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

from tensdireito_content_engine.domain import RawItem
from tensdireito_content_engine.storage.database import to_utc_iso, transaction
from tensdireito_content_engine.storage.endpoints import mark_endpoint_success


@dataclass(frozen=True, slots=True)
class SavedItems:
    new: int
    existing: int


def save_endpoint_items(
    conn: sqlite3.Connection,
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


def _exists(conn: sqlite3.Connection, item: RawItem) -> bool:
    row = conn.execute(
        "SELECT 1 FROM raw_item WHERE source_endpoint_id = ? AND url = ? AND content_hash = ?",
        (item.source_endpoint_id, item.url, item.content_hash),
    ).fetchone()
    return row is not None


def _insert(conn: sqlite3.Connection, item: RawItem, run_id: int, timestamp: str) -> None:
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
