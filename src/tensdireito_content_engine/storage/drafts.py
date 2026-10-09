"""Persistência da fila de rascunhos WhatsApp e da revisão humana."""

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from tensdireito_content_engine.domain.enums import VerificationStatus
from tensdireito_content_engine.domain.policy import MINIMUM_RELEVANCE_SCORE
from tensdireito_content_engine.storage.database import to_utc_iso, transaction
from tensdireito_content_engine.storage.errors import StorageError
from tensdireito_content_engine.storage.interfaces import Connection
from tensdireito_content_engine.storage.schema import open_existing_database

PENDING = "pending"
APPROVED = "approved"
PUBLISHED = "published"


@dataclass(frozen=True, slots=True)
class WhatsAppDraft:
    id: int
    raw_item_id: int
    editorial_score: float
    verification_status: VerificationStatus
    status: str
    message: str


def create_pending_draft(
    conn: Connection, raw_item_id: int, editorial_score: float, message: str, at: datetime
) -> int | None:
    """Insere um rascunho pendente uma única vez por item; repetições são idempotentes."""
    timestamp = to_utc_iso(at)
    try:
        with transaction(conn, f"a gravação do rascunho do item {raw_item_id} falhou"):
            exists = conn.execute(
                "SELECT id FROM whatsapp_draft WHERE raw_item_id = ?", (raw_item_id,)
            ).fetchone()
            if exists is not None:
                return None
            cursor = conn.execute(
                "INSERT INTO whatsapp_draft (raw_item_id, editorial_score, "
                "verification_status, status, message, created_at, updated_at, approved_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    raw_item_id,
                    editorial_score,
                    VerificationStatus.UNVERIFIED.value,
                    PENDING,
                    message,
                    timestamp,
                    timestamp,
                ),
            )
            draft_id = cursor.lastrowid
    except sqlite3.Error as exc:
        raise StorageError(f"não foi possível guardar o rascunho WhatsApp: {exc}") from exc
    if draft_id is None:
        raise StorageError("não foi possível obter o identificador do rascunho WhatsApp")
    return int(draft_id)


def persist_pending_drafts(
    path: Path,
    drafts: Sequence[tuple[int, float, str]],
    at: datetime,
) -> int:
    """Persiste rascunhos elegíveis e devolve quantos foram criados nesta execução."""
    conn = open_existing_database(Path(path))
    try:
        return sum(
            create_pending_draft(conn, raw_item_id, score, message, at) is not None
            for raw_item_id, score, message in drafts
        )
    finally:
        conn.close()


def list_drafts(path: Path, *, status: str | None = PENDING) -> tuple[WhatsAppDraft, ...]:
    """Lista rascunhos por ID; por omissão mostra apenas os pendentes."""
    conn = open_existing_database(Path(path))
    try:
        if status is None:
            rows = conn.execute(
                "SELECT id, raw_item_id, editorial_score, verification_status, status, message "
                "FROM whatsapp_draft ORDER BY id"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, raw_item_id, editorial_score, verification_status, status, message "
                "FROM whatsapp_draft WHERE status = ? ORDER BY id",
                (status,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise StorageError(f"não foi possível listar rascunhos WhatsApp: {exc}") from exc
    finally:
        conn.close()
    return tuple(
        WhatsAppDraft(
            id=int(row[0]),
            raw_item_id=int(row[1]),
            editorial_score=float(row[2]),
            verification_status=VerificationStatus(row[3]),
            status=row[4],
            message=row[5],
        )
        for row in rows
    )


def export_approved_drafts(
    path: Path,
    verification_statuses: Sequence[VerificationStatus],
    at: datetime,
    *,
    mark_published: bool = False,
) -> tuple[WhatsAppDraft, ...]:
    """Devolve rascunhos aprovados verificados; opcionalmente marca-os publicados."""
    if not verification_statuses or any(
        not isinstance(status, VerificationStatus)
        or status
        not in {
            VerificationStatus.VERIFIED_EDITORIAL,
            VerificationStatus.VERIFIED_OFFICIAL,
        }
        for status in verification_statuses
    ):
        raise ValueError("a exportação exige verificação editorial ou oficial explícita")

    conn = open_existing_database(Path(path))
    placeholders = ", ".join("?" for _ in verification_statuses)
    try:
        with transaction(conn, "a exportação dos rascunhos WhatsApp falhou"):
            rows = conn.execute(
                "SELECT id, raw_item_id, editorial_score, verification_status, status, message "
                "FROM whatsapp_draft WHERE status = ? "
                f"AND verification_status IN ({placeholders}) ORDER BY id",
                (APPROVED, *(status.value for status in verification_statuses)),
            ).fetchall()
            if mark_published and rows:
                draft_ids = tuple(int(row[0]) for row in rows)
                id_placeholders = ", ".join("?" for _ in draft_ids)
                cursor = conn.execute(
                    "UPDATE whatsapp_draft SET status = ?, updated_at = ? "
                    f"WHERE status = ? AND id IN ({id_placeholders})",
                    (PUBLISHED, to_utc_iso(at), APPROVED, *draft_ids),
                )
                if cursor.rowcount != len(draft_ids):
                    raise StorageError(
                        "nem todos os rascunhos exportados foram marcados publicados"
                    )
    except sqlite3.Error as exc:
        raise StorageError(f"não foi possível exportar rascunhos WhatsApp: {exc}") from exc
    finally:
        conn.close()

    return tuple(
        WhatsAppDraft(
            id=int(row[0]),
            raw_item_id=int(row[1]),
            editorial_score=float(row[2]),
            verification_status=VerificationStatus(row[3]),
            status=PUBLISHED if mark_published else row[4],
            message=row[5],
        )
        for row in rows
    )


def approve_draft(
    path: Path,
    draft_id: int,
    verification_status: VerificationStatus,
    at: datetime,
) -> bool:
    """Aprova explicitamente um rascunho validado por uma pessoa."""
    if verification_status not in {
        VerificationStatus.VERIFIED_EDITORIAL,
        VerificationStatus.VERIFIED_OFFICIAL,
    }:
        raise ValueError("a aprovação exige verificação editorial ou oficial explícita")
    conn = open_existing_database(Path(path))
    try:
        with transaction(conn, f"a aprovação do rascunho {draft_id} falhou"):
            cursor = conn.execute(
                "UPDATE whatsapp_draft SET verification_status = ?, status = ?, "
                "approved_at = ?, updated_at = ? WHERE id = ? AND status = ? "
                "AND editorial_score >= ? AND EXISTS ("
                "SELECT 1 FROM raw_item r "
                "JOIN source_endpoint e ON e.id = r.source_endpoint_id "
                "JOIN source_registry s ON s.id = e.source_id "
                "WHERE r.id = whatsapp_draft.raw_item_id AND s.registry_status = 'validated')",
                (
                    verification_status.value,
                    APPROVED,
                    to_utc_iso(at),
                    to_utc_iso(at),
                    draft_id,
                    PENDING,
                    MINIMUM_RELEVANCE_SCORE,
                ),
            )
            approved = cursor.rowcount == 1
    except sqlite3.Error as exc:
        raise StorageError(f"não foi possível aprovar o rascunho WhatsApp: {exc}") from exc
    finally:
        conn.close()
    return approved
