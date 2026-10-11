"""Execução diária: recolha persistida, normalização, deduplicação e relatório."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from tensdireito_content_engine.collect import CollectResult, run_collect
from tensdireito_content_engine.collectors import CollectorRegistry
from tensdireito_content_engine.domain.policy import MINIMUM_RELEVANCE_SCORE
from tensdireito_content_engine.normalize import (
    NormalizedItem,
    RawContentError,
    deduplicate_exact,
    extract_rss_item,
    normalize_raw_item,
)
from tensdireito_content_engine.publish.whatsapp import WhatsAppMessage, format_whatsapp_message
from tensdireito_content_engine.scoring import load_topic_terms, score_item
from tensdireito_content_engine.sources import load_sources
from tensdireito_content_engine.storage import (
    StoredRawItem,
    init_database,
    list_raw_items,
    persist_pending_drafts,
    sync_sources,
)

LISBON = ZoneInfo("Europe/Lisbon")
DEFAULT_REPORT_DIR = Path("data") / "reports" / "daily"


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


@dataclass(frozen=True, slots=True)
class DailyResult:
    day: date
    collection: CollectResult
    normalized: int
    duplicates: int
    articles: tuple[DailyArticle, ...]
    report_path: Path
    drafts_created: int


def run_daily(
    db_path: Path,
    config_path: Path,
    report_dir: Path,
    registry: CollectorRegistry,
    *,
    day: date | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
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

    candidates: list[tuple[StoredRawItem, NormalizedItem]] = []
    scores_by_raw_item: dict[int, float] = {}
    for stored in list_raw_items(db_path):
        normalized = normalize_raw_item(stored.item)
        scores_by_raw_item[stored.id] = score_item(normalized, topics).value
        # DEC-057: só notícias com data de publicação do próprio dia (Lisboa); sem data
        # ou com uma data antiga no URL, o item é descartado.
        published = normalized.published_at
        if published is None or published.astimezone(LISBON).date() != selected_day:
            continue
        if _url_date(stored.item.url) not in (None, selected_day):
            continue
        candidates.append((stored, normalized))

    deduplicated = deduplicate_exact(normalized for _, normalized in candidates)
    records_by_item = {id(normalized): stored for stored, normalized in candidates}
    articles = [
        DailyArticle(
            title=item.title,
            url=item.raw_item.url,
            source_name=records_by_item[id(item)].source_name,
            published_at=item.published_at,
            fetched_at=item.raw_item.fetched_at,
            raw_item_id=records_by_item[id(item)].id,
            registry_status=records_by_item[id(item)].registry_status,
            editorial_score=scores_by_raw_item[records_by_item[id(item)].id],
            excerpt=_source_excerpt(item.raw_item.raw_content),
        )
        for item in deduplicated.representatives
    ]
    articles.sort(key=_article_order)

    draft_candidates = [
        (article.raw_item_id, article.editorial_score, _render_draft(article))
        for article in articles
        if article.editorial_score >= MINIMUM_RELEVANCE_SCORE
        and article.registry_status == "validated"
        and _is_https_url(article.url)
    ]
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
                "",
            )
        )
    return "\n".join(lines).rstrip() + "\n"


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


TOPICS_FILENAME = "apoios.yaml"
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


def _render_draft(article: DailyArticle) -> str:
    message = WhatsAppMessage(
        emoji="📢",
        title=_shorten(article.title, TITLE_MAX_CHARS),
        key_points=_key_points(article.excerpt),
        cta="Saiba mais",
        url=article.url,
    )
    return format_whatsapp_message(message)
