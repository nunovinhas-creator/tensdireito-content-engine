"""`tde sources sync`: projecção do registo de fontes em SQLite (ROADMAP.md M2.7).

DEC-027, DEC-028, DEC-029 e DEC-030:

- unidireccional YAML → SQLite: recebe objectos de domínio (`SourceRegistry`,
  `SourceEndpoint`) já validados pela leitura do M2.5; nunca escreve no YAML e não
  importa `sources`;
- exige uma base criada por `tde init` com o esquema conforme às migrações; não cria a
  base de dados nem aplica migrações;
- reconcilia pelo `id`, só nos campos projectados; `last_success_at` e `last_error`
  nunca são tocados; `fetch` fica fora da projecção (coluna nula na inserção);
- `updated_at` só muda quando um campo projectado muda (comparação na forma guardada);
- remoções e mudanças de `source_id`/`endpoint_type` de endpoints referenciados por
  `raw_item` são conflitos: todos são reportados e nada é escrito;
- tudo numa única transacção explícita; qualquer erro → rollback integral.

Só `SELECT`, `INSERT`, `UPDATE` e `DELETE` simples (DEC-013); sem `INSERT OR REPLACE`.
"""

import json
import sqlite3
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from tensdireito_content_engine.domain import SourceEndpoint, SourceRegistry
from tensdireito_content_engine.storage.database import connect, to_utc_iso
from tensdireito_content_engine.storage.errors import StorageError
from tensdireito_content_engine.storage.migrator import (
    applied_migrations,
    load_migrations,
    pending_migrations,
)

# Campos projectados do YAML (ROADMAP.md M2.7, *Campos*), pela ordem das colunas.
SOURCE_FIELDS = (
    "id",
    "name",
    "entity_type",
    "tier",
    "categories",
    "domains",
    "registry_status",
    "validated_at",
    "validated_by",
    "notes",
)
ENDPOINT_FIELDS = (
    "id",
    "source_id",
    "endpoint_type",
    "url",
    "endpoint_status",
    "validated_at",
    "validated_by",
)

_INIT_HINT = "execute `tde init`"

Row = tuple[object, ...]


class SourceSyncError(StorageError):
    """A sincronização falhou sem alterar a base de dados. `errors` lista todos os motivos."""

    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("\n".join(self.errors))


@dataclass(frozen=True, slots=True)
class SyncCounts:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0


@dataclass(frozen=True, slots=True)
class SyncResult:
    path: Path
    sources: SyncCounts
    endpoints: SyncCounts

    @property
    def total(self) -> SyncCounts:
        return SyncCounts(
            inserted=self.sources.inserted + self.endpoints.inserted,
            updated=self.sources.updated + self.endpoints.updated,
            unchanged=self.sources.unchanged + self.endpoints.unchanged,
            removed=self.sources.removed + self.endpoints.removed,
        )


@dataclass(frozen=True, slots=True)
class _Plan:
    """Escritas a fazer numa tabela, por ordem determinista."""

    insert: tuple[Row, ...]
    update: tuple[Row, ...]
    unchanged: int
    remove: tuple[str, ...]

    def counts(self) -> SyncCounts:
        return SyncCounts(
            inserted=len(self.insert),
            updated=len(self.update),
            unchanged=self.unchanged,
            removed=len(self.remove),
        )


def source_row(source: SourceRegistry) -> Row:
    """`SourceRegistry` → valores guardados de `SOURCE_FIELDS`."""
    return (
        source.id,
        source.name,
        source.entity_type.value,
        source.tier.value,
        _json_list(source.categories),
        _json_list(source.domains),
        source.registry_status.value,
        _optional_iso(source.validated_at),
        source.validated_by,
        source.notes,
    )


def endpoint_row(endpoint: SourceEndpoint) -> Row:
    """`SourceEndpoint` → valores guardados de `ENDPOINT_FIELDS` (sem `fetch` nem estado)."""
    return (
        endpoint.id,
        endpoint.source_id,
        endpoint.endpoint_type.value,
        endpoint.url,
        endpoint.endpoint_status.value,
        _optional_iso(endpoint.validated_at),
        endpoint.validated_by,
    )


def sync_sources(
    path: Path,
    sources: Iterable[SourceRegistry],
    endpoints: Iterable[SourceEndpoint],
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> SyncResult:
    """Sincroniza o registo validado com `source_registry` e `source_endpoint`.

    Erros de pré-condição → `StorageError`; conflitos de reconciliação →
    `SourceSyncError` com todos os motivos. Em ambos os casos a base fica inalterada.
    """
    path = Path(path)
    if not path.exists():
        # Verificado antes de `connect()`, que criaria o ficheiro e o directório pai.
        raise StorageError(f"a base de dados não existe; {_INIT_HINT} para a criar")
    source_rows = [source_row(source) for source in sources]
    endpoint_rows = [endpoint_row(endpoint) for endpoint in endpoints]

    conn = connect(path)
    try:
        _check_schema(conn)
        return _reconcile(conn, path, source_rows, endpoint_rows, to_utc_iso(now()))
    finally:
        conn.close()


def _check_schema(conn: sqlite3.Connection) -> None:
    """O esquema tem de estar conforme às migrações do código; o sync não migra."""
    try:
        pending = pending_migrations(applied_migrations(conn), load_migrations())
    except StorageError as exc:
        raise StorageError(f"esquema não conforme: {exc}; {_INIT_HINT}") from exc
    if pending:
        names = ", ".join(migration.name for migration in pending)
        raise StorageError(f"esquema não conforme: migrações pendentes: {names}; {_INIT_HINT}")


def _reconcile(
    conn: sqlite3.Connection,
    path: Path,
    source_rows: list[Row],
    endpoint_rows: list[Row],
    timestamp: str,
) -> SyncResult:
    conn.execute("BEGIN")
    try:
        stored_sources = _stored(conn, "source_registry", SOURCE_FIELDS)
        stored_endpoints = _stored(conn, "source_endpoint", ENDPOINT_FIELDS)
        referenced = _referenced_endpoints(conn)

        source_plan = _plan(source_rows, stored_sources)
        endpoint_plan = _plan(endpoint_rows, stored_endpoints)
        conflicts = _conflicts(source_plan, endpoint_plan, stored_endpoints, referenced)
        if conflicts:
            raise SourceSyncError(conflicts)

        # Ordem compatível com a FK `source_endpoint.source_id`, sem `ON DELETE` (DEC-029).
        for row in source_plan.insert:
            _insert(conn, "source_registry", SOURCE_FIELDS, row, timestamp)
        for row in source_plan.update:
            _update(conn, "source_registry", SOURCE_FIELDS, row, timestamp)
        for row in endpoint_plan.insert:
            _insert(conn, "source_endpoint", ENDPOINT_FIELDS, row, timestamp)
        for row in endpoint_plan.update:
            _update(conn, "source_endpoint", ENDPOINT_FIELDS, row, timestamp)
        for endpoint_id in endpoint_plan.remove:
            conn.execute("DELETE FROM source_endpoint WHERE id = ?", (endpoint_id,))
        for source_id in source_plan.remove:
            conn.execute("DELETE FROM source_registry WHERE id = ?", (source_id,))
    except sqlite3.Error as exc:
        conn.execute("ROLLBACK")
        raise StorageError(f"a sincronização falhou: {exc}") from exc
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
    return SyncResult(path=path, sources=source_plan.counts(), endpoints=endpoint_plan.counts())


def _stored(conn: sqlite3.Connection, table: str, fields: tuple[str, ...]) -> dict[str, Row]:
    """Linhas existentes, só nos campos projectados, indexadas pelo `id`."""
    rows = conn.execute(f"SELECT {', '.join(fields)} FROM {table} ORDER BY id").fetchall()
    return {row[0]: tuple(row) for row in rows}


def _referenced_endpoints(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT DISTINCT source_endpoint_id FROM raw_item WHERE source_endpoint_id IS NOT NULL"
    ).fetchall()
    return {endpoint_id for (endpoint_id,) in rows}


def _plan(rows: list[Row], stored: dict[str, Row]) -> _Plan:
    insert: list[Row] = []
    update: list[Row] = []
    unchanged = 0
    for row in rows:
        current = stored.get(row[0])
        if current is None:
            insert.append(row)
        elif current != row:
            update.append(row)
        else:
            unchanged += 1
    wanted = {row[0] for row in rows}
    remove = tuple(sorted(row_id for row_id in stored if row_id not in wanted))
    return _Plan(insert=tuple(insert), update=tuple(update), unchanged=unchanged, remove=remove)


def _conflicts(
    source_plan: _Plan,
    endpoint_plan: _Plan,
    stored_endpoints: dict[str, Row],
    referenced: set[str],
) -> list[str]:
    """Conflitos de DEC-029, por ordem determinista. Lista vazia → pode escrever."""
    source_id_at = ENDPOINT_FIELDS.index("source_id")
    type_at = ENDPOINT_FIELDS.index("endpoint_type")
    conflicts: list[str] = []

    for row in endpoint_plan.update:
        endpoint_id = row[0]
        if endpoint_id not in referenced:
            continue
        current = stored_endpoints[endpoint_id]
        for at, field in ((source_id_at, "source_id"), (type_at, "endpoint_type")):
            if current[at] != row[at]:
                conflicts.append(
                    f"endpoint {endpoint_id}: {field} mudou ({current[at]} → {row[at]}), mas o "
                    "endpoint é referenciado por raw_item; represente-o como um endpoint novo, "
                    "com id novo"
                )

    for endpoint_id in endpoint_plan.remove:
        if endpoint_id in referenced:
            conflicts.append(
                f"endpoint {endpoint_id}: retirado do YAML, mas é referenciado por raw_item; "
                "mantenha-o no YAML (ex.: como INACTIVE)"
            )

    for source_id in source_plan.remove:
        used = sorted(
            endpoint_id
            for endpoint_id, current in stored_endpoints.items()
            if current[source_id_at] == source_id and endpoint_id in referenced
        )
        if used:
            conflicts.append(
                f"fonte {source_id}: retirada do YAML, mas é referenciada por raw_item "
                f"através de {', '.join(used)}; mantenha-a no YAML (ex.: como INACTIVE)"
            )
    return conflicts


def _insert(
    conn: sqlite3.Connection, table: str, fields: tuple[str, ...], row: Row, timestamp: str
) -> None:
    columns = (*fields, "created_at", "updated_at")
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        (*row, timestamp, timestamp),
    )


def _update(
    conn: sqlite3.Connection, table: str, fields: tuple[str, ...], row: Row, timestamp: str
) -> None:
    """Sobrescreve só os campos projectados e `updated_at`; os restantes ficam intactos."""
    assignments = ", ".join(f"{field} = ?" for field in (*fields[1:], "updated_at"))
    conn.execute(
        f"UPDATE {table} SET {assignments} WHERE id = ?",
        (*row[1:], timestamp, row[0]),
    )


def _json_list(values: tuple[str, ...]) -> str:
    return json.dumps(list(values), ensure_ascii=False)


def _optional_iso(value: datetime | None) -> str | None:
    return None if value is None else to_utc_iso(value)
