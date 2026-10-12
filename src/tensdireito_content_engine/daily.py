"""Execução diária: recolha persistida, normalização, deduplicação e relatório."""

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from tensdireito_content_engine.ai_draft import write_whatsapp
from tensdireito_content_engine.collect import CollectResult, run_collect
from tensdireito_content_engine.collectors import CollectorRegistry
from tensdireito_content_engine.llm import LoadedLLM
from tensdireito_content_engine.normalize import (
    ExactDuplicate,
    NormalizedItem,
    RawContentError,
    deduplicate_exact,
    extract_rss_item,
    normalize_raw_item,
)
from tensdireito_content_engine.normalize_command import run_normalize
from tensdireito_content_engine.priority import Priority, classify, load_priority_terms
from tensdireito_content_engine.publish.whatsapp import WhatsAppMessage, format_whatsapp_message
from tensdireito_content_engine.scoring import load_topic_terms, score_item
from tensdireito_content_engine.similarity import same_topic
from tensdireito_content_engine.sources import load_sources
from tensdireito_content_engine.storage import (
    StorageError,
    StoredRawItem,
    init_database,
    list_raw_items,
    persist_pending_drafts,
    sync_sources,
)
from tensdireito_content_engine.storage.candidates import (
    ARCHIVED,
    DISCOVERED,
    DRAFTED,
    GROUPED,
    IN_GROUP,
    METHODS,
    OUT_OF_DAY,
    CandidateStats,
    Observation,
    record_observations,
)
from tensdireito_content_engine.topics import TOPICS_FILENAME, TopicMap, load_topic_map
from tensdireito_content_engine.url_key import UrlKeyError, url_key

LISBON = ZoneInfo("Europe/Lisbon")
DEFAULT_REPORT_DIR = Path("data") / "reports" / "daily"

# DEC-063: tecto de rascunhos por run; os excedentes ficam no relatório com o motivo.
MAX_DRAFTS_PER_RUN = 20

# Decisões registadas por notícia do dia (DEC-063). Nenhuma apaga o candidato.
DECISION_DRAFT = "rascunho"
DECISION_REVIEW = "aguarda classificação (fase 3)"
DECISION_ARCHIVED = "arquivada"
DECISION_UNVALIDATED = "fonte não validada"
DECISION_NOT_HTTPS = "URL não HTTPS"
DECISION_LIMIT = f"limite de {MAX_DRAFTS_PER_RUN} rascunhos por run"


@dataclass(frozen=True, slots=True)
class DailyArticle:
    title: str
    url: str
    source_name: str
    published_at: datetime | None
    fetched_at: datetime
    raw_item_id: int
    registry_status: str | None
    editorial_score: float
    excerpt: str | None
    source_tier: str | None = None
    # DEC-063: prioridade (alta/rever/baixa), o motivo e o que aconteceu ao candidato.
    priority: str = Priority.LOW.value
    priority_reason: str = ""
    priority_rule: str = ""
    decision: str = ""


@dataclass(frozen=True, slots=True)
class DailyResult:
    day: date
    collection: CollectResult
    normalized: int
    duplicates: int
    articles: tuple[DailyArticle, ...]
    report_path: Path
    drafts_created: int
    ai_drafts: int = 0
    # Fase 2a (DEC-068): registo de candidatos e resultado do `tde normalize` interno.
    candidate_stats: CandidateStats | None = None
    candidates_without_key: int = 0
    normalize_status: str = ""

    def priority_counts(self) -> dict[str, int]:
        """Notícias do dia por prioridade, sempre com as três chaves."""
        counts = Counter(article.priority for article in self.articles)
        return {level.value: counts.get(level.value, 0) for level in Priority}

    def by_priority(self, level: Priority) -> tuple[DailyArticle, ...]:
        return tuple(article for article in self.articles if article.priority == level.value)


def run_daily(
    db_path: Path,
    config_path: Path,
    report_dir: Path,
    registry: CollectorRegistry,
    *,
    day: date | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    writer: LoadedLLM | None = None,
) -> DailyResult:
    """Executa toda a fase diária; a repetição não duplica `raw_item` nem o relatório."""
    instant = now()

    def fixed_now() -> datetime:
        return instant

    loaded = load_sources(config_path)
    init_database(db_path, now=fixed_now)
    sync_sources(db_path, loaded.sources, loaded.endpoints, now=fixed_now)
    # DEC-072: mínimos por endpoint, do YAML, para o canário de fonte suspeita.
    minimums = {
        endpoint.id: endpoint.expect_min_items
        for endpoint in loaded.endpoints
        if endpoint.expect_min_items is not None
    }
    collection = run_collect(db_path, registry, now=fixed_now, expect_min_items=minimums)
    # DEC-064: o documento de cada captura fica em `source_document`. Uma falha aqui não
    # impede o resto do run; fica registada no resumo.
    try:
        normalize_status = run_normalize(db_path, now=fixed_now).status
    except StorageError as exc:
        normalize_status = f"falhou: {exc}"
    selected_day = day or instant.astimezone(LISBON).date()
    topics = load_topic_terms(Path(config_path).parent / TOPICS_FILENAME)
    topic_map = load_topic_map(Path(config_path).parent / TOPICS_FILENAME)
    priority_terms = load_priority_terms(Path(config_path).parent / TOPICS_FILENAME)

    candidates: list[tuple[StoredRawItem, NormalizedItem]] = []
    scores_by_raw_item: dict[int, float] = {}
    # Fase 2a: tudo o que foi recolhido hoje é registado como candidato, com a origem da
    # data de publicação; o que não é do dia passa a `fora_do_dia`.
    seen_today: list[tuple[StoredRawItem, NormalizedItem, str, str]] = []
    stored_items = list_raw_items(db_path)
    # DEC-061: primeira recolha de cada endpoint, para datar itens sem `pubDate`.
    first_seen_by_endpoint: dict[str | None, date] = {}
    for stored in stored_items:
        seen = stored.item.fetched_at.astimezone(LISBON).date()
        endpoint = stored.item.source_endpoint_id
        if endpoint not in first_seen_by_endpoint or seen < first_seen_by_endpoint[endpoint]:
            first_seen_by_endpoint[endpoint] = seen
    for stored in stored_items:
        normalized = normalize_raw_item(stored.item)
        # DEC-059: fontes oficiais (T1/T2) passam à frente das restantes.
        scores_by_raw_item[stored.id] = min(
            100.0,
            score_item(normalized, topics).value + TIER_BONUS.get(stored.source_tier or "", 0),
        )
        # DEC-057: só notícias com data de publicação do próprio dia (Lisboa); sem data
        # ou com uma data antiga no URL, o item é descartado.
        published = normalized.published_at
        seen = stored.item.fetched_at.astimezone(LISBON).date()
        if published is None:
            # Sem data: só conta se o item apareceu hoje pela primeira vez num endpoint que
            # já tinha sido recolhido antes (com a base persistida, DEC-061).
            endpoint_start = first_seen_by_endpoint.get(stored.item.source_endpoint_id, seen)
            in_day = seen == selected_day and endpoint_start < selected_day
            date_source = "first_seen" if in_day else "none"
            out_reason = "sem data de publicação fiável"
        else:
            in_day = published.astimezone(LISBON).date() == selected_day
            # DEC-069: a data do news sitemap tem origem própria.
            date_source = "sitemap" if stored.endpoint_type == "news_sitemap" else "feed"
            out_reason = "publicada noutro dia"
        if in_day and _url_date(stored.item.url) not in (None, selected_day):
            in_day = False
            out_reason = "data no URL de outro dia"
        if seen == selected_day or in_day:
            seen_today.append((stored, normalized, date_source, "" if in_day else out_reason))
        if not in_day:
            continue
        candidates.append((stored, normalized))

    deduplicated = deduplicate_exact(normalized for _, normalized in candidates)
    records_by_item = {id(normalized): stored for stored, normalized in candidates}
    articles: list[DailyArticle] = []
    for item in deduplicated.representatives:
        stored = records_by_item[id(item)]
        # DEC-063: a prioridade substitui o limiar 65 como critério; o score só ordena.
        decision = classify(item.title, item.text, stored.source_tier, priority_terms)
        articles.append(
            DailyArticle(
                title=item.title,
                url=item.raw_item.url,
                source_name=stored.source_name,
                published_at=item.published_at,
                fetched_at=item.raw_item.fetched_at,
                raw_item_id=stored.id,
                registry_status=stored.registry_status,
                editorial_score=scores_by_raw_item[stored.id],
                excerpt=_source_excerpt(item.raw_item.raw_content),
                source_tier=stored.source_tier,
                priority=decision.level.value,
                priority_reason=decision.reason,
                priority_rule=decision.rule.value,
            )
        )
    articles.sort(key=_article_order)

    decisions: dict[int, str] = {}
    eligible: list[DailyArticle] = []
    for article in articles:
        if article.priority == Priority.REVIEW.value:
            decisions[article.raw_item_id] = DECISION_REVIEW
        elif article.priority == Priority.LOW.value:
            decisions[article.raw_item_id] = DECISION_ARCHIVED
        elif article.registry_status != "validated":
            decisions[article.raw_item_id] = DECISION_UNVALIDATED
        elif not _is_https_url(article.url):
            decisions[article.raw_item_id] = DECISION_NOT_HTTPS
        else:
            eligible.append(article)
    # DEC-059: notícias do mesmo tema dão um único rascunho, o de maior score.
    representatives: list[DailyArticle] = []
    group_of: dict[int, int] = {}
    for article in sorted(eligible, key=lambda a: (-a.editorial_score, _article_order(a))):
        kept = next((k for k in representatives if same_topic(article.title, k.title)), None)
        if kept is not None:
            decisions[article.raw_item_id] = f"mesmo tema que «{_shorten(kept.title, 60)}»"
            group_of[article.raw_item_id] = kept.raw_item_id
        elif len(representatives) >= MAX_DRAFTS_PER_RUN:
            decisions[article.raw_item_id] = DECISION_LIMIT
        else:
            representatives.append(article)
            decisions[article.raw_item_id] = DECISION_DRAFT
    articles = [replace(a, decision=decisions[a.raw_item_id]) for a in articles]
    composed = [
        (article, *_compose_draft(article, topic_map, writer)) for article in representatives
    ]
    draft_candidates = [
        (article.raw_item_id, article.editorial_score, message) for article, message, _ in composed
    ]
    ai_drafts = sum(1 for _, _, used_ai in composed if used_ai)
    report_dir = Path(report_dir)
    report_path = report_dir / f"{selected_day.isoformat()}.txt"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        _render_report(selected_day, len(candidates), len(deduplicated.duplicates), articles),
        encoding="utf-8",
    )
    drafts_created = persist_pending_drafts(db_path, draft_candidates, instant)
    observations, without_key = _observations(
        _joinable_hosts(loaded.sources),
        seen_today,
        {a.raw_item_id: a for a in articles},
        group_of,
        _duplicate_of(deduplicated.duplicates, records_by_item),
    )
    candidate_stats = record_observations(db_path, observations, collection.run_id, instant)
    return DailyResult(
        day=selected_day,
        collection=collection,
        normalized=len(candidates),
        duplicates=len(deduplicated.duplicates),
        articles=tuple(articles),
        report_path=report_path,
        drafts_created=drafts_created,
        ai_drafts=ai_drafts,
        candidate_stats=candidate_stats,
        candidates_without_key=without_key,
        normalize_status=normalize_status,
    )


def _duplicate_of(
    duplicates: tuple[ExactDuplicate, ...], records_by_item: dict[int, StoredRawItem]
) -> dict[int, int]:
    """Captura duplicada exacta → captura que a representa (ids de `raw_item`)."""
    return {
        records_by_item[id(dup.item)].id: records_by_item[id(dup.duplicate_of)].id
        for dup in duplicates
    }


def discovery_method(stored: StoredRawItem) -> str:
    """Método de descoberta de uma captura: as pesquisas do Bing contam como `search`."""
    host = (urlsplit(stored.endpoint_url or "").hostname or "").lower()
    if host == "bing.com" or host.endswith(".bing.com"):
        return "search"
    return stored.endpoint_type if stored.endpoint_type in METHODS else "rss"


def candidate_target(
    article: DailyArticle | None, out_reason: str, group_of: int | None
) -> tuple[str, str, int | None]:
    """Estado de destino de uma captura na fase 2a, a partir da decisão da fase 1."""
    if article is None:
        return OUT_OF_DAY, out_reason or "fora da janela do dia", None
    if article.priority == Priority.LOW.value:
        return ARCHIVED, article.priority_reason, None
    if article.priority == Priority.REVIEW.value:
        return DISCOVERED, article.priority_reason, None
    if article.decision == DECISION_DRAFT:
        return DRAFTED, "rascunho criado", None
    if group_of is not None:
        return IN_GROUP, article.decision, group_of
    return GROUPED, article.decision, None


def _joinable_hosts(sources) -> frozenset[str]:
    """Anfitriões cuja forma `www.` se junta à forma sem `www.` (§4.1; DEC-069).

    Só quando a mesma fonte declara as duas formas em `domains`.
    """
    hosts: set[str] = set()
    for source in sources:
        domains = {domain.lower() for domain in source.domains}
        for domain in domains:
            if domain.startswith("www.") and domain[4:] in domains:
                hosts |= {domain, domain[4:]}
    return frozenset(hosts)


def _observations(
    joinable_hosts: frozenset[str],
    seen_today: list[tuple[StoredRawItem, NormalizedItem, str, str]],
    articles: dict[int, DailyArticle],
    group_of: dict[int, int],
    duplicate_of: dict[int, int],
) -> tuple[list[Observation], int]:
    observations: list[Observation] = []
    without_key = 0
    for stored, normalized, date_source, out_reason in seen_today:
        endpoint = stored.item.source_endpoint_id
        try:
            key = url_key(stored.item.url, joinable_hosts)
        except UrlKeyError:
            without_key += 1
            continue
        if endpoint is None:
            without_key += 1
            continue
        representative = duplicate_of.get(stored.id)
        article = articles.get(representative if representative is not None else stored.id)
        target, reason, group = candidate_target(article, out_reason, group_of.get(stored.id))
        if representative is not None and article is not None:
            # Duplicado exacto: segue o representante; se este deu rascunho, fica no grupo.
            reason = f"duplicado exacto de «{_shorten(article.title, 60)}»"
            if target == DRAFTED:
                target, group = IN_GROUP, representative
        observations.append(
            Observation(
                raw_item_id=stored.id,
                endpoint_id=endpoint,
                method=discovery_method(stored),
                url_key=key,
                url=stored.item.url,
                title=normalized.title,
                summary=_source_excerpt(stored.item.raw_content),
                source_id=stored.source_id,
                source_tier=stored.source_tier or "T3",
                published_at=normalized.published_at,
                published_at_source=date_source,
                seen_at=stored.item.fetched_at,
                priority=article.priority if article else Priority.LOW.value,
                priority_reason=(article.priority_reason if article else "fora da janela do dia"),
                target=target,
                target_reason=reason,
                group_of_raw_item_id=group,
            )
        )
    return observations, without_key


def _article_order(article: DailyArticle) -> tuple[float, str, str, str, int]:
    effective_date = article.published_at or article.fetched_at
    return (
        -effective_date.timestamp(),
        article.source_name.casefold(),
        article.title.casefold(),
        article.url,
        article.raw_item_id,
    )


def _render_report(
    day: date, normalized: int, duplicates: int, articles: list[DailyArticle]
) -> str:
    lines = [
        "TensDireito — Notícias do dia",
        day.strftime("%d/%m/%Y"),
        "",
        f"{len(articles)} notícias selecionadas",
        f"{normalized} normalizadas; {duplicates} duplicadas",
        _priority_line(articles),
        "",
    ]
    if not articles:
        lines.append("Não foram encontradas notícias na janela diária.")
    for position, article in enumerate(articles, start=1):
        published = (
            article.published_at.astimezone(LISBON).strftime("%d/%m/%Y %H:%M")
            if article.published_at is not None
            else "não indicada"
        )
        lines.extend(
            (
                f"{position}. {article.title}",
                f"   Fonte: {article.source_name}",
                f"   Data: {published}",
                f"   URL: {article.url}",
                f"   Prioridade: {article.priority} — {article.priority_reason}",
                f"   Decisão: {article.decision}",
                "",
            )
        )
    return "\n".join(lines).rstrip() + "\n"


def _priority_line(articles: list[DailyArticle]) -> str:
    counts = Counter(article.priority for article in articles)
    return "Prioridade: " + "; ".join(
        f"{level.value} {counts.get(level.value, 0)}" for level in Priority
    )


def _source_excerpt(raw_content: str) -> str | None:
    """Obtém um excerto literal do resumo RSS, sem o reescrever nem o verificar."""
    try:
        return extract_rss_item(raw_content).text
    except RawContentError:
        return None


_URL_DATE = re.compile(r"(?<!\d)(20\d{2})[/-](0[1-9]|1[0-2])[/-](0[1-9]|[12]\d|3[01])(?!\d)")


def _url_date(url: str) -> date | None:
    """Data `AAAA/MM/DD` ou `AAAA-MM-DD` no caminho do URL, se existir e for válida."""
    match = _URL_DATE.search(urlsplit(url).path)
    if match is None:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def _is_https_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and "\n" not in value
        and "\r" not in value
    )


TIER_BONUS = {"T1": 10, "T2": 5}
TITLE_MAX_CHARS = 90
POINT_MAX_CHARS = 160
POINTS_MAX = 3
POINTS_TOTAL_MAX_CHARS = 380
FALLBACK_POINT = "Veja todos os detalhes na notícia completa."
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ0-9\"“«(])")


def _shorten(text: str, limit: int) -> str:
    """Corta `text` numa fronteira de palavra, com reticências, se exceder `limit`."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:–-")
    return f"{cut}…"


def _key_points(excerpt: str | None) -> tuple[str, ...]:
    """Até 3 frases curtas do excerpt da fonte, dentro do orçamento de caracteres (DEC-053)."""
    if not excerpt:
        return ("Resumo pendente de revisão editorial.", FALLBACK_POINT)
    points: list[str] = []
    used = 0
    for sentence in _SENTENCE_END.split(" ".join(excerpt.split())):
        sentence = sentence.strip()
        if not sentence:
            continue
        point = _shorten(sentence, POINT_MAX_CHARS)
        if points and used + len(point) > POINTS_TOTAL_MAX_CHARS:
            break
        points.append(point)
        used += len(point)
        if len(points) == POINTS_MAX:
            break
    if not points:
        points.append(_shorten(excerpt, POINT_MAX_CHARS))
    if len(points) < 2:
        points.append(FALLBACK_POINT)
    return tuple(points)


def _render_draft(
    article: DailyArticle, topic_map: TopicMap | None = None, writer: LoadedLLM | None = None
) -> str:
    return _compose_draft(article, topic_map, writer)[0]


def _compose_draft(
    article: DailyArticle, topic_map: TopicMap | None, writer: LoadedLLM | None
) -> tuple[str, bool]:
    """Mensagem do rascunho e se foi redigida por IA (DEC-059/DEC-060)."""
    # DEC-058: se o título refere um apoio com guia no tensdireito.com, o link é o guia;
    # a fonte original continua registada no rascunho e na issue.
    guide = (topic_map or TopicMap()).guide_for(article.title)
    # DEC-059: com IA configurada, título e pontos são uma proposta validada do modelo;
    # sem IA ou se a proposta falhar a validação, usam-se as frases da fonte.
    proposal = write_whatsapp(writer, article.title, article.excerpt)
    message = WhatsAppMessage(
        emoji=proposal.emoji if proposal else "📢",
        title=proposal.title if proposal else _shorten(article.title, TITLE_MAX_CHARS),
        key_points=proposal.key_points if proposal else _key_points(article.excerpt),
        cta="Saiba quem tem direito e como pedir" if guide else "Saiba mais",
        url=guide or article.url,
    )
    return format_whatsapp_message(message), proposal is not None
