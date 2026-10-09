"""Execução diária: recolha persistida, normalização, deduplicação e relatório."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tensdireito_content_engine.collect import CollectResult, run_collect
from tensdireito_content_engine.collectors import CollectorRegistry
from tensdireito_content_engine.normalize import (
    NormalizedItem,
    deduplicate_exact,
    normalize_raw_item,
)
from tensdireito_content_engine.sources import load_sources
from tensdireito_content_engine.storage import (
    StoredRawItem,
    init_database,
    list_raw_items,
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


@dataclass(frozen=True, slots=True)
class DailyResult:
    day: date
    collection: CollectResult
    normalized: int
    duplicates: int
    articles: tuple[DailyArticle, ...]
    report_path: Path


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

    candidates: list[tuple[StoredRawItem, NormalizedItem]] = []
    for stored in list_raw_items(db_path):
        normalized = normalize_raw_item(stored.item)
        relevant_date = normalized.published_at or stored.item.fetched_at
        if relevant_date.astimezone(LISBON).date() == selected_day:
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
        )
        for item in deduplicated.representatives
    ]
    articles.sort(key=_article_order)

    report_dir = Path(report_dir)
    report_path = report_dir / f"{selected_day.isoformat()}.txt"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        _render_report(selected_day, len(candidates), len(deduplicated.duplicates), articles),
        encoding="utf-8",
    )
    return DailyResult(
        day=selected_day,
        collection=collection,
        normalized=len(candidates),
        duplicates=len(deduplicated.duplicates),
        articles=tuple(articles),
        report_path=report_path,
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