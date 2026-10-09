"""Repositório de `source_document` e leitura dos `raw_item` pendentes (ROADMAP.md M2.11).

DEC-022, DEC-041. Todo o SQL de `tde normalize` vive aqui; a orquestração não tem SQL.

- **Pendentes:** `raw_item` sem `source_document`, por ordem crescente de `id`, com o
  `endpoint_type` do seu endpoint e o `tier`/`registry_status` da sua fonte. São lidos
  em lotes, sem carregar todos em memória, e limitados aos `raw_item` que existiam no
  início da leitura; cada lote é lido depois de o anterior ter sido processado, pelo que
  um item que continue pendente (`unsupported`/`failed`) não é relido na mesma execução.
- **Inserção** numa transacção por item, que inclui a procura do representante: um
  documento com `text_hash` igual ao de um representante já registado (`duplicate_of`
  nulo) fica `ignored`, com `duplicate_of` igual ao `id` desse representante; senão é
  ele próprio representante (`normalized`). `text_hash` nulo nunca é duplicado. O
  representante já registado não é alterado. Sem `INSERT OR IGNORE`, `INSERT OR REPLACE`
  nem `ON CONFLICT` (DEC-013); o `UNIQUE (raw_item_id)` da `0002` é a barreira final.
"""

import dataclasses
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime

from tensdireito_content_engine.domain import DocumentStatus, SourceDocument
from tensdireito_content_engine.storage.database import to_utc_iso, transaction
from tensdireito_content_engine.storage.errors import StorageError
from tensdireito_content_engine.storage.interfaces import Connection

PENDING_BATCH_SIZE = 100


@dataclass(frozen=True, slots=True)
class PendingRawItem:
    """Um `raw_item` pendente, com o que o NORMALIZE precisa, tal como está guardado."""

    id: int
    source_endpoint_id: str | None
    title: str
    raw_content: str
    published_at_raw: str | None
    endpoint_type: str | None  # nulo sem endpoint
    source_id: str | None  # fonte do endpoint; nula sem endpoint
    tier: str | None  # da fonte
    registry_status: str | None  # da fonte, no momento da leitura


def pending_raw_items(
    conn: Connection, batch_size: int = PENDING_BATCH_SIZE
) -> Iterator[PendingRawItem]:
    """Os `raw_item` pendentes, por `id`, lidos em lotes. Erro SQLite → `StorageError`."""
    upper = _read(conn, "SELECT MAX(id) FROM raw_item", ())[0][0]
    if upper is None:
        return
    after = 0
    while True:
        rows = _read(
            conn,
            "SELECT r.id, r.source_endpoint_id, r.title, r.raw_content, r.published_at_raw, "
            "e.endpoint_type, e.source_id, s.tier, s.registry_status "
            "FROM raw_item r "
            "LEFT JOIN source_endpoint e ON e.id = r.source_endpoint_id "
            "LEFT JOIN source_registry s ON s.id = e.source_id "
            "WHERE r.id > ? AND r.id <= ? AND NOT EXISTS "
            "(SELECT 1 FROM source_document d WHERE d.raw_item_id = r.id) "
            "ORDER BY r.id LIMIT ?",
            (after, upper, batch_size),
        )
        if not rows:
            return
        for row in rows:
            yield PendingRawItem(*row)
        after = rows[-1][0]


def insert_source_document(
    conn: Connection, document: SourceDocument, run_id: int, at: datetime
) -> SourceDocument:
    """Grava um documento numa transacção própria e devolve-o como ficou guardado.

    `document` chega sem `id`, com `duplicate_of` nulo e `status = normalized`; a
    deduplicação decide aqui, dentro da transacção, `duplicate_of` e `status`.
    Erro SQLite → rollback e `StorageError`.
    """
    if document.id is not None or document.duplicate_of is not None:
        raise ValueError("o documento a inserir não tem id nem duplicate_of")
    if document.status is not DocumentStatus.NORMALIZED:
        raise ValueError("o documento a inserir chega com status normalized")
    timestamp = to_utc_iso(at)
    with transaction(conn, f"a gravação do documento do raw_item {document.raw_item_id} falhou"):
        if document.text_hash is not None:
            representative = _representative(conn, document.text_hash)
            if representative is not None:
                document = dataclasses.replace(
                    document, duplicate_of=representative, status=DocumentStatus.IGNORED
                )
        cursor = conn.execute(
            "INSERT INTO source_document (raw_item_id, source_id, canonical_url, title, text, "
            "language, published_at, source_tier, document_kind, text_hash, duplicate_of, "
            "status, created_in_run, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                document.raw_item_id,
                document.source_id,
                document.canonical_url,
                document.title,
                document.text,
                document.language,
                None if document.published_at is None else to_utc_iso(document.published_at),
                document.source_tier.value,
                None if document.document_kind is None else document.document_kind.value,
                document.text_hash,
                document.duplicate_of,
                document.status.value,
                run_id,
                timestamp,
                timestamp,
            ),
        )
        document_id = cursor.lastrowid
    assert document_id is not None
    return dataclasses.replace(document, id=document_id)


def _representative(conn: Connection, text_hash: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM source_document WHERE text_hash = ? AND duplicate_of IS NULL "
        "ORDER BY id LIMIT 1",
        (text_hash,),
    ).fetchone()
    return None if row is None else int(row[0])


def _read(
    conn: Connection, sql: str, params: tuple[object, ...]
) -> list[tuple[object, ...]]:
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.Error as exc:
        raise StorageError(f"não foi possível ler os raw_item pendentes: {exc}") from exc
