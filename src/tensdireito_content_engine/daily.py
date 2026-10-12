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
    NormalizedItem,
    RawContentError,
    deduplicate_exact,
    extract_rss_item,
    normalize_raw_item,
)
from tensdireito_content_engine.priority import Priority, classify, load_priority_terms
from tensdireito_content_engine.publish.whatsapp import WhatsAppMessage, format_whatsapp_message
from tensdireito_content_engine.scoring import load_topic_terms, score_item
from tensdireito_content_engine.similarity import same_topic
from tensdireito_content_engine.sources import load_sources
from tensdireito_content_engine.storage import (
    StoredRawItem,
    init_database,
    list_raw_items,
    persist_pending_drafts,
    sync_sources,
)
from tensdireito_content_engine.topics import TOPICS_FILENAME, TopicMap, load_topic_map

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
    collection = run_collect(db_path, registry, now=fixed_now)
    selected_day = day or instant.astimezone(LISBON).date()
    topics = load_topic_terms(Path(config_path).parent / TOPICS_FILENAME)
    topic_map = load_topic_map(Path(config_path).parent / TOPICS_FILENAME)
    priority_terms = load_priority_terms(Path(config_path).parent / TOPICS_FILENAME)

    candidates: list[tuple[StoredRawItem, NormalizedItem]] = []
    scores_by_raw_item: dict[int, float] = {}
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
        if published is None:
            # Sem data: só conta se o item apareceu hoje pela primeira vez num endpoint que
            # já tinha sido recolhido antes (com a base persistida, DEC-061).
            seen = stored.item.fetched_at.astimezone(LISBON).date()
            endpoint_start = first_seen_by_endpoint.get(stored.item.source_endpoint_id, seen)
            if seen != selected_day or endpoint_start >= selected_day:
                continue
        elif published.astimezone(LISBON).date() != selected_day:
            continue
        if _url_date(stored.item.url) not in (None, selected_day):
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
    for article in sorted(eligible, key=lambda a: (-a.editorial_score, _article_order(a))):
        kept = next((k for k in representatives if same_topic(article.title, k.title)), None)
        if kept is not None:
            decisions[article.raw_item_id] = f"mesmo tema que «{_shorten(kept.title, 60)}»"
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
    return DailyResult(
        day=selected_day,
        collection=collection,
        normalized=len(candidates),
        duplicates=len(deduplicated.duplicates),
        articles=tuple(articles),
        report_path=report_path,
        drafts_created=drafts_created,
        ai_drafts=ai_drafts,
    )


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
