"""Orquestração de `tde normalize` (ROADMAP.md M2.11; DEC-041).

Liga a leitura dos `raw_item` pendentes, a extracção e normalização (`normalize/`) e a
persistência de `source_document`, sem SQL: todo o acesso à base de dados passa pelas
funções de `storage`. Local, sem rede e sem IA; não lê `config/sources.yaml`.

- Pré-condições, antes de criar o `run`: base existente e esquema conforme, com a
  `0002` aplicada. Nada é criado nem migrado.
- `run` no padrão de DEC-031: `command = "normalize"`, fechado com `status` e `stats`.
- Cada pendente, por ordem de `id`, tem um de quatro resultados: `normalized` ou
  `duplicate` (documento criado numa transacção própria), `unsupported` (sem regra de
  extracção; continua pendente e não é falha) ou `failed` (`raw_content` ilegível ou
  erro de validação do domínio; continua pendente, sem escrita).
- Um erro da `storage` não é falha de item: propaga-se como `StorageError` e deixa o
  `run` com `finished_at` nulo (execução interrompida); os documentos já confirmados
  mantêm-se.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from tensdireito_content_engine.domain import (
    DocumentStatus,
    DomainValidationError,
    EndpointType,
    RegistryStatus,
    SourceDocument,
    SourceTier,
)
from tensdireito_content_engine.normalize import (
    RawContentError,
    extract_rss_item,
    normalize_published_at,
    normalize_title,
    text_fingerprint,
)
from tensdireito_content_engine.storage import (
    Connection,
    PendingRawItem,
    finish_run,
    insert_source_document,
    open_existing_database,
    pending_raw_items,
    start_run,
)

COMMAND = "normalize"
SUCCESS = "success"
PARTIAL = "partial"
FAILED = "failed"

NORMALIZED = "normalized"
DUPLICATE = "duplicate"
UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class ItemOutcome:
    raw_item_id: int
    result: str  # normalized | duplicate | unsupported | failed
    reason: str | None = None  # só em unsupported e failed
    without_text: bool = False  # documento criado com `text` nulo


@dataclass(frozen=True, slots=True)
class NormalizeResult:
    path: Path
    run_id: int
    status: str  # success | partial | failed
    items: tuple[ItemOutcome, ...]

    def count(self, result: str) -> int:
        return sum(1 for outcome in self.items if outcome.result == result)

    @property
    def without_text(self) -> int:
        return sum(
            1 for outcome in self.items if outcome.result == NORMALIZED and outcome.without_text
        )

    def stats(self) -> dict[str, object]:
        """`run.stats` (ROADMAP.md M2.11): só `unsupported` e `failed` em `items`."""
        return {
            "items": [
                {
                    "raw_item_id": outcome.raw_item_id,
                    "result": outcome.result,
                    "reason": outcome.reason,
                }
                for outcome in self.items
                if outcome.result in (UNSUPPORTED, FAILED)
            ],
            "totals": {
                "pending": len(self.items),
                "normalized": self.count(NORMALIZED),
                "duplicates": self.count(DUPLICATE),
                "without_text": self.without_text,
                "unsupported": self.count(UNSUPPORTED),
                "failed": self.count(FAILED),
            },
        }


def run_normalize(
    path: Path, now: Callable[[], datetime] = lambda: datetime.now(UTC)
) -> NormalizeResult:
    """Normaliza os `raw_item` pendentes e devolve o resultado do `run` concluído.

    Pré-condições → `StorageError`, sem `run`. Erro da `storage` durante a execução →
    `StorageError`, com o `run` por concluir.
    """
    path = Path(path)
    conn = open_existing_database(path)
    try:
        run_id = start_run(conn, COMMAND, now())
        outcomes = [
            _normalize_item(conn, pending, run_id, now) for pending in pending_raw_items(conn)
        ]
        result = NormalizeResult(
            path=path, run_id=run_id, status=_status(outcomes), items=tuple(outcomes)
        )
        finish_run(conn, run_id, result.status, result.stats(), now())
    finally:
        conn.close()
    return result


def build_document(pending: PendingRawItem) -> SourceDocument:
    """Campos do documento de um pendente `rss` (ROADMAP.md M2.11, *Esquema*).

    `raw_content` ilegível → `RawContentError`; dados que violam o domínio →
    `DomainValidationError`. O documento chega sem `id`, com `duplicate_of` nulo e
    `status = normalized`; a deduplicação é decidida na inserção.
    """
    extraction = extract_rss_item(pending.raw_content)
    text = extraction.text
    return SourceDocument(
        raw_item_id=pending.id,
        source_id=pending.source_id,
        canonical_url=None,  # D12 OPEN (DEC-037)
        title=normalize_title(pending.title),
        text=text,
        language=extraction.language,
        published_at=normalize_published_at(pending.published_at_raw),
        source_tier=source_tier(pending.tier, pending.registry_status),
        document_kind=None,  # não determinado (DEC-039)
        text_hash=None if text is None else text_fingerprint(text),
        duplicate_of=None,
        status=DocumentStatus.NORMALIZED,
    )


def source_tier(tier: str | None, registry_status: str | None) -> SourceTier:
    """Tier da fonte `VALIDATED` no momento da normalização; senão `T4` (SOURCES.md §3.1)."""
    if registry_status != RegistryStatus.VALIDATED.value:
        return SourceTier.T4
    try:
        return SourceTier(tier)
    except ValueError:
        raise DomainValidationError(f"source_tier tem de ser SourceTier: {tier!r}") from None


def _normalize_item(
    conn: Connection, pending: PendingRawItem, run_id: int, now: Callable[[], datetime]
) -> ItemOutcome:
    if pending.source_endpoint_id is None:
        return ItemOutcome(pending.id, UNSUPPORTED, "sem endpoint")
    if pending.endpoint_type != EndpointType.RSS.value:
        return ItemOutcome(
            pending.id,
            UNSUPPORTED,
            f"sem regra de extracção para endpoint_type {pending.endpoint_type}",
        )
    try:
        document = build_document(pending)
    except RawContentError as exc:
        return ItemOutcome(pending.id, FAILED, f"raw_content: {exc}")
    except DomainValidationError as exc:
        return ItemOutcome(pending.id, FAILED, str(exc))
    stored = insert_source_document(conn, document, run_id, now())
    if stored.status is DocumentStatus.IGNORED:
        return ItemOutcome(pending.id, DUPLICATE)
    return ItemOutcome(pending.id, NORMALIZED, without_text=stored.text is None)


def _status(outcomes: list[ItemOutcome]) -> str:
    failed = sum(1 for outcome in outcomes if outcome.result == FAILED)
    if failed == 0:
        return SUCCESS
    created = sum(1 for outcome in outcomes if outcome.result in (NORMALIZED, DUPLICATE))
    return PARTIAL if created else FAILED
