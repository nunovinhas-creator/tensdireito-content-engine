"""Repositório de `raw_item` (DATA_MODEL.md §2.1; ROADMAP.md M2.8; DEC-021, DEC-031).

Identidade `(source_endpoint_id, url, content_hash)`: um item cuja identidade já existe
— de uma execução anterior ou de um item anterior do mesmo `fetch` — não é inserido nem
alterado e conta como `existing`. A verificação é um `SELECT` antes do `INSERT`, dentro
da transacção do endpoint; o `UNIQUE` da `0001` continua a ser a barreira final. Sem
`INSERT OR IGNORE`, `INSERT OR REPLACE` nem `ON CONFLICT` (DEC-013).
"""

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from tensdireito_content_engine.domain import RawItem
from tensdireito_content_engine.storage.database import to_utc_iso, transaction
from tensdireito_content_engine.storage.endpoints import mark_endpoint_success
from tensdireito_content_engine.storage.errors import StorageError
from tensdireito_content_engine.storage.interfaces import Connection
from tensdireito_content_engine.storage.schema import open_existing_database


@dataclass(frozen=True, slots=True)
class SavedItems:
    new: int
    existing: int


@dataclass(frozen=True, slots=True)
class StoredRawItem:
    id: int
    item: RawItem
    source_id: str | None
    source_name: str


def list_raw_items(path: Path) -> tuple[StoredRawItem, ...]:
    """Lê itens persistidos com a identidade da fonte, ordenados deterministicamente."""
    conn = open_existing_database(Path(path))
    try:
        rows = conn.execute(
            "SELECT r.id, r.url, r.title, r.raw_content, r.fetched_at, r.source_endpoint_id, "
            "r.external_id, r.published_at_raw, r.manual_note, s.id, s.name "
            "FROM raw_item r LEFT JOIN source_endpoint e ON e.id = r.source_endpoint_id "
            "LEFT JOIN source_registry s ON s.id = e.source_id "
            "ORDER BY r.fetched_at, r.source_endpoint_id, r.url, r.id"
        ).fetchall()
    except sqlite3.Error as exc:
        raise StorageError(f"não foi possível ler raw_item: {exc}") from exc
    finally:
        conn.close()

    return tuple(
        StoredRawItem(
            id=row[0],
            item=RawItem(
                url=row[1],
                title=row[2],
                raw_content=row[3],
                fetched_at=datetime.fromisoformat(row[4]),
                source_endpoint_id=row[5],
                external_id=row[6],
                published_at_raw=row[7],
                manual_note=row[8],
            ),
            source_id=row[9],
            source_name=row[10] or "Fonte não identificada",
        )
        for row in rows
    )


def save_endpoint_items(
    conn: Connection,
    endpoint_id: str,
    items: Sequence[RawItem],
    run_id: int,
    at: datetime,
) -> SavedItems:
    """Grava os itens de um endpoint e marca o seu sucesso, numa única transacção.

    Os itens têm de ter `source_endpoint_id == endpoint_id` (a proveniência é validada
    por quem chama; aqui é uma garantia). Erro SQLite → rollback e `StorageError`.
    """
    for item in items:
        if item.source_endpoint_id != endpoint_id:
            raise ValueError(f"item de outro endpoint: {item.source_endpoint_id}")
    timestamp = to_utc_iso(at)
    new = existing = 0
    with transaction(conn, f"a gravação do endpoint {endpoint_id} falhou"):
        for item in items:
            if _exists(conn, item):
                existing += 1
                continue
            _insert(conn, item, run_id, timestamp)
            new += 1
        mark_endpoint_success(conn, endpoint_id, at)
    return SavedItems(new=new, existing=existing)


def _exists(conn: Connection, item: RawItem) -> bool:
    row = conn.execute(
        "SELECT 1 FROM raw_item WHERE source_endpoint_id = ? AND url = ? AND content_hash = ?",
        (item.source_endpoint_id, item.url, item.content_hash),
    ).fetchone()
    return row is not None


def _insert(conn: Connection, item: RawItem, run_id: int, timestamp: str) -> None:
    conn.execute(
        "INSERT INTO raw_item (source_endpoint_id, url, external_id, title, raw_content, "
        "fetched_at, published_at_raw, content_hash, manual_note, created_in_run, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            item.source_endpoint_id,
            item.url,
            item.external_id,
            item.title,
            item.raw_content,
            to_utc_iso(item.fetched_at),
            item.published_at_raw,
            item.content_hash,
            item.manual_note,
            run_id,
            timestamp,
            timestamp,
        ),
    )
