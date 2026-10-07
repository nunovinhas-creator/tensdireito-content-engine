"""Orquestração de `tde collect` (ROADMAP.md M2.8; DEC-031).

Liga a selecção de endpoints, o registo de collectors e a persistência, sem SQL:
todo o acesso à base de dados passa pelas funções de `storage`.

- Pré-condições, antes de criar o `run`: base existente, esquema conforme e, com
  `--source`, fonte existente em `source_registry`. Nada é criado nem migrado.
- Endpoints `ACTIVE` do espelho SQLite, por `id`; `config/sources.yaml` não é lido.
- Atomicidade por endpoint: a falha de um endpoint (collector em falta, excepção do
  collector na chamada ou na iteração, item inválido ou de outra proveniência) não grava
  nenhum item desse endpoint, regista `last_error` e não impede os restantes.
- Um erro da `storage` não é falha de endpoint: propaga-se como `StorageError` e deixa o
  `run` com `finished_at` nulo (execução interrompida).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from tensdireito_content_engine.collectors import CollectorRegistry
from tensdireito_content_engine.domain import RawItem, SourceEndpoint
from tensdireito_content_engine.storage import (
    Connection,
    active_endpoints,
    finish_run,
    open_existing_database,
    record_endpoint_failure,
    save_endpoint_items,
    source_exists,
    start_run,
)

COMMAND = "collect"
SUCCESS = "success"
PARTIAL = "partial"
FAILED = "failed"


class CollectError(Exception):
    """Falha de pré-condição que não é da `storage` (ex.: fonte inexistente)."""


@dataclass(frozen=True, slots=True)
class EndpointOutcome:
    id: str
    result: str  # success | failed
    new: int = 0
    existing: int = 0
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CollectResult:
    path: Path
    run_id: int
    status: str  # success | partial | failed
    endpoints: tuple[EndpointOutcome, ...]

    @property
    def succeeded(self) -> int:
        return sum(1 for outcome in self.endpoints if outcome.result == SUCCESS)

    @property
    def failed(self) -> int:
        return sum(1 for outcome in self.endpoints if outcome.result == FAILED)

    @property
    def new(self) -> int:
        return sum(outcome.new for outcome in self.endpoints)

    @property
    def existing(self) -> int:
        return sum(outcome.existing for outcome in self.endpoints)

    def stats(self) -> dict[str, object]:
        """`run.stats`, com os endpoints pela ordem de selecção (ROADMAP.md M2.8)."""
        return {
            "endpoints": [
                {
                    "id": outcome.id,
                    "result": outcome.result,
                    "new": outcome.new,
                    "existing": outcome.existing,
                    "error": outcome.error,
                }
                for outcome in self.endpoints
            ],
            "totals": {
                "selected": len(self.endpoints),
                "succeeded": self.succeeded,
                "failed": self.failed,
                "new": self.new,
                "existing": self.existing,
            },
        }


def run_collect(
    path: Path,
    registry: CollectorRegistry,
    source_id: str | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> CollectResult:
    """Executa a recolha local e devolve o resultado do `run` concluído.

    Pré-condições → `StorageError` ou `CollectError`, sem `run`. Erro da `storage`
    durante a execução → `StorageError`, com o `run` por concluir.
    """
    path = Path(path)
    conn = open_existing_database(path)
    try:
        if source_id is not None and not source_exists(conn, source_id):
            raise CollectError(f"a fonte {source_id} não existe em source_registry")
        run_id = start_run(conn, COMMAND, now())
        outcomes: list[EndpointOutcome] = []
        for endpoint in active_endpoints(conn, source_id):
            outcomes.append(_collect_endpoint(conn, registry, endpoint, run_id, now))
        result = CollectResult(
            path=path, run_id=run_id, status=_status(outcomes), endpoints=tuple(outcomes)
        )
        finish_run(conn, run_id, result.status, result.stats(), now())
    finally:
        conn.close()
    return result


def _collect_endpoint(
    conn: Connection,
    registry: CollectorRegistry,
    endpoint: SourceEndpoint,
    run_id: int,
    now: Callable[[], datetime],
) -> EndpointOutcome:
    items, error = _fetch(registry, endpoint)
    if error is not None:
        record_endpoint_failure(conn, endpoint.id, error)
        return EndpointOutcome(id=endpoint.id, result=FAILED, error=error)
    saved = save_endpoint_items(conn, endpoint.id, items, run_id, now())
    return EndpointOutcome(id=endpoint.id, result=SUCCESS, new=saved.new, existing=saved.existing)


def _fetch(
    registry: CollectorRegistry, endpoint: SourceEndpoint
) -> tuple[list[RawItem], str | None]:
    """Itens do collector, todos validados antes de qualquer escrita; ou o motivo da falha."""
    collector = registry.get(endpoint.endpoint_type)
    if collector is None:
        return [], f"sem collector para endpoint_type {endpoint.endpoint_type.value}"
    try:
        items = list(collector.fetch(endpoint, None))  # M2.8: `since` é sempre `None`.
    except Exception as exc:
        return [], f"o collector falhou: {type(exc).__name__}: {exc}"
    for position, item in enumerate(items, start=1):
        if not isinstance(item, RawItem):
            return [], f"item {position}: não é um RawItem"
        if item.source_endpoint_id != endpoint.id:
            return [], (
                f"item {position}: source_endpoint_id {item.source_endpoint_id} "
                f"diferente do endpoint {endpoint.id}"
            )
    return items, None


def _status(outcomes: list[EndpointOutcome]) -> str:
    failed = sum(1 for outcome in outcomes if outcome.result == FAILED)
    if failed == 0:
        return SUCCESS
    if failed == len(outcomes):
        return FAILED
    return PARTIAL
