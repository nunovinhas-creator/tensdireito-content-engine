"""Leitura de endpoints e estado operacional de `source_endpoint` (ROADMAP.md M2.8; DEC-031).

- `active_endpoints` lê o espelho SQLite (nunca `config/sources.yaml`) e devolve
  `SourceEndpoint` de domínio `ACTIVE`, ordenados por `id`.
- `last_success_at` e `last_error` são campos operacionais (DEC-027): actualizá-los não
  altera campos projectados nem `updated_at` (DEC-028).
"""

import sqlite3
from datetime import datetime

from tensdireito_content_engine.domain import (
    DomainValidationError,
    EndpointStatus,
    EndpointType,
    SourceEndpoint,
)
from tensdireito_content_engine.storage.database import to_utc_iso, transaction
from tensdireito_content_engine.storage.errors import StorageError
from tensdireito_content_engine.storage.interfaces import Connection

_COLUMNS = (
    "id, source_id, endpoint_type, url, endpoint_status, validated_at, validated_by, "
    "last_success_at, last_error"
)


def source_exists(conn: Connection, source_id: str) -> bool:
    try:
        row = conn.execute("SELECT 1 FROM source_registry WHERE id = ?", (source_id,)).fetchone()
    except sqlite3.Error as exc:
        raise StorageError(f"não foi possível ler source_registry: {exc}") from exc
    return row is not None


def active_endpoints(
    conn: Connection, source_id: str | None = None
) -> list[SourceEndpoint]:
    """Endpoints `ACTIVE`, por `id`; com `source_id`, só os dessa fonte."""
    sql = f"SELECT {_COLUMNS} FROM source_endpoint WHERE endpoint_status = ?"
    params: tuple[str, ...] = (EndpointStatus.ACTIVE.value,)
    if source_id is not None:
        sql += " AND source_id = ?"
        params += (source_id,)
    try:
        rows = conn.execute(sql + " ORDER BY id", params).fetchall()
    except sqlite3.Error as exc:
        raise StorageError(f"não foi possível ler source_endpoint: {exc}") from exc
    return [_endpoint(row) for row in rows]


def mark_endpoint_success(conn: Connection, endpoint_id: str, at: datetime) -> None:
    """Sucesso: `last_success_at` actualizado e `last_error` nulo.

    Corre dentro da transacção do endpoint, aberta por quem chama.
    """
    conn.execute(
        "UPDATE source_endpoint SET last_success_at = ?, last_error = NULL WHERE id = ?",
        (to_utc_iso(at), endpoint_id),
    )


def record_endpoint_failure(conn: Connection, endpoint_id: str, error: str) -> None:
    """Falha: `last_error` actualizado, `last_success_at` preservado; transacção própria."""
    with transaction(conn, f"não foi possível registar a falha do endpoint {endpoint_id}"):
        conn.execute("UPDATE source_endpoint SET last_error = ? WHERE id = ?", (error, endpoint_id))


def _endpoint(row: tuple[object, ...]) -> SourceEndpoint:
    endpoint_id = row[0]
    try:
        return SourceEndpoint(
            id=row[0],
            source_id=row[1],
            endpoint_type=EndpointType(row[2]),
            url=row[3],
            endpoint_status=EndpointStatus(row[4]),
            validated_at=_optional_datetime(row[5]),
            validated_by=row[6],
            last_success_at=_optional_datetime(row[7]),
            last_error=row[8],
        )
    except (DomainValidationError, ValueError, TypeError) as exc:
        raise StorageError(f"endpoint {endpoint_id} inválido na base de dados: {exc}") from exc


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"data inválida: {value!r}")
    return datetime.fromisoformat(value)
