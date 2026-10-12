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

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from tensdireito_content_engine.collectors import CollectorRegistry
from tensdireito_content_engine.collectors.http import LIMITATION, REDIRECT, RETRY
from tensdireito_content_engine.domain import RawItem, SourceEndpoint
from tensdireito_content_engine.storage import (
    Connection,
    active_endpoints,
    finish_run,
    open_existing_database,
    previous_run_stats,
    record_endpoint_failure,
    save_endpoint_items,
    source_exists,
    start_run,
)

COMMAND = "collect"
SUCCESS = "success"
PARTIAL = "partial"
FAILED = "failed"

# DEC-072 (especificação §3.3 e §5): estado de cada endpoint no run.
STATE_OK = "ok"
STATE_EMPTY = "vazio"  # respondeu bem, sem itens
STATE_SUSPECT = "suspeito"  # abaixo de `expect_min_items` em 2 runs seguidos
STATE_FAILED = "falha"
STATES = (STATE_OK, STATE_EMPTY, STATE_SUSPECT, STATE_FAILED)


class CollectError(Exception):
    """Falha de pré-condição que não é da `storage` (ex.: fonte inexistente)."""


@dataclass(frozen=True, slots=True)
class EndpointOutcome:
    id: str
    result: str  # success | failed
    new: int = 0
    existing: int = 0
    error: str | None = None
    # DEC-070: limitações, novas tentativas e redirects seguidos neste endpoint.
    notes: tuple[str, ...] = ()
    # DEC-072: estado no run e aviso quando o problema se repete do run anterior.
    state: str = STATE_OK
    warning: str | None = None

    @property
    def items(self) -> int:
        return self.new + self.existing


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

    def state_counts(self) -> dict[str, int]:
        """Endpoints por estado (DEC-072), sempre com os quatro estados."""
        counts = dict.fromkeys(STATES, 0)
        for outcome in self.endpoints:
            counts[outcome.state] += 1
        return counts

    @property
    def warnings(self) -> tuple[EndpointOutcome, ...]:
        return tuple(outcome for outcome in self.endpoints if outcome.warning)

    def transport_counts(self) -> dict[str, int]:
        """Contagens de DEC-066/070 para o resumo: o que o transporte fez além do pedido."""
        counts = {LIMITATION: 0, RETRY: 0, REDIRECT: 0, "redirect recusado": 0}
        for outcome in self.endpoints:
            for note in outcome.notes:
                kind = note.split(":", 1)[0]
                if kind in counts:
                    counts[kind] += 1
            if outcome.error and "redirect recusado" in outcome.error:
                counts["redirect recusado"] += 1
        return counts

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
                    "notes": list(outcome.notes),
                    "state": outcome.state,
                    "warning": outcome.warning,
                }
                for outcome in self.endpoints
            ],
            "totals": {
                "selected": len(self.endpoints),
                "succeeded": self.succeeded,
                "failed": self.failed,
                "new": self.new,
                "existing": self.existing,
                "transport": self.transport_counts(),
                "states": self.state_counts(),
            },
        }


def run_collect(
    path: Path,
    registry: CollectorRegistry,
    source_id: str | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    expect_min_items: Mapping[str, int] | None = None,
) -> CollectResult:
    """Executa a recolha local e devolve o resultado do `run` concluído.

    `expect_min_items` (DEC-072): mínimo por endpoint, do YAML; o estado de cada endpoint
    compara-se com o `run` de recolha anterior.

    Pré-condições → `StorageError` ou `CollectError`, sem `run`. Erro da `storage`
    durante a execução → `StorageError`, com o `run` por concluir.
    """
    path = Path(path)
    conn = open_existing_database(path)
    try:
        if source_id is not None and not source_exists(conn, source_id):
            raise CollectError(f"a fonte {source_id} não existe em source_registry")
        run_id = start_run(conn, COMMAND, now())
        previous = _previous_outcomes(previous_run_stats(conn, COMMAND, run_id))
        minimums = expect_min_items or {}
        outcomes: list[EndpointOutcome] = []
        for endpoint in active_endpoints(conn, source_id):
            outcome = _collect_endpoint(conn, registry, endpoint, run_id, now)
            outcomes.append(_with_health(outcome, previous.get(endpoint.id), minimums))
        result = CollectResult(
            path=path, run_id=run_id, status=_status(outcomes), endpoints=tuple(outcomes)
        )
        finish_run(conn, run_id, result.status, result.stats(), now())
    finally:
        conn.close()
    return result


def _previous_outcomes(stats: dict | None) -> dict[str, tuple[str, int]]:
    """Resultado e itens de cada endpoint no run anterior; entradas mal formadas ignoradas."""
    if not stats or not isinstance(stats.get("endpoints"), list):
        return {}
    previous: dict[str, tuple[str, int]] = {}
    for entry in stats["endpoints"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        new, existing = entry.get("new"), entry.get("existing")
        if not isinstance(new, int) or not isinstance(existing, int):
            continue
        previous[entry["id"]] = (str(entry.get("result")), new + existing)
    return previous


def _with_health(
    outcome: EndpointOutcome,
    previous: tuple[str, int] | None,
    minimums: Mapping[str, int],
) -> EndpointOutcome:
    """Estado do endpoint (DEC-072): falha, suspeito, vazio ou ok, com aviso se repetido."""
    if outcome.result == FAILED:
        repeated = previous is not None and previous[0] == FAILED
        warning = "falha em 2 runs seguidos" if repeated else None
        return replace(outcome, state=STATE_FAILED, warning=warning)
    minimum = minimums.get(outcome.id)
    if minimum is not None and outcome.items < minimum:
        if previous is not None and previous[0] == SUCCESS and previous[1] < minimum:
            warning = f"abaixo do mínimo esperado ({outcome.items} < {minimum}) em 2 runs seguidos"
            return replace(outcome, state=STATE_SUSPECT, warning=warning)
    if outcome.items == 0:
        return replace(outcome, state=STATE_EMPTY)
    return replace(outcome, state=STATE_OK)


def _collect_endpoint(
    conn: Connection,
    registry: CollectorRegistry,
    endpoint: SourceEndpoint,
    run_id: int,
    now: Callable[[], datetime],
) -> EndpointOutcome:
    registry.drain_events()  # o que sobrou de outro endpoint não é deste
    items, error = _fetch(registry, endpoint)
    notes = tuple(f"{event.kind}: {event.detail}" for event in registry.drain_events())
    if error is not None:
        record_endpoint_failure(conn, endpoint.id, error)
        return EndpointOutcome(id=endpoint.id, result=FAILED, error=error, notes=notes)
    saved = save_endpoint_items(conn, endpoint.id, items, run_id, now())
    return EndpointOutcome(
        id=endpoint.id, result=SUCCESS, new=saved.new, existing=saved.existing, notes=notes
    )


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
