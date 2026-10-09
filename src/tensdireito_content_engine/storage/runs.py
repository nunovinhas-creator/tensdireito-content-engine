"""Repositório de `run` (DATA_MODEL.md §2.9; ROADMAP.md M2.8; DEC-031).

Sem modelo de domínio `Run` nem estado `running`: durante a execução, `finished_at` e
`status` são nulos; `outcome` e `report_path` ficam nulos no M2.8. Cada escrita é uma
transacção própria.
"""

import json
from collections.abc import Mapping
from datetime import datetime

from tensdireito_content_engine.storage.database import to_utc_iso, transaction
from tensdireito_content_engine.storage.interfaces import Connection

RUN_STATUSES = ("success", "partial", "failed")


def start_run(conn: Connection, command: str, started_at: datetime) -> int:
    """Insere um `run` em curso e devolve o seu `id`."""
    timestamp = to_utc_iso(started_at)
    with transaction(conn, "não foi possível criar o run"):
        cursor = conn.execute(
            "INSERT INTO run (command, started_at, finished_at, status, stats, outcome, "
            "report_path, created_at, updated_at) "
            "VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, ?, ?)",
            (command, timestamp, timestamp, timestamp),
        )
        run_id = cursor.lastrowid
    assert run_id is not None
    return run_id


def finish_run(
    conn: Connection,
    run_id: int,
    status: str,
    stats: Mapping[str, object],
    finished_at: datetime,
) -> None:
    """Grava `finished_at`, `status` e `stats` (JSON) de um `run` em curso."""
    if status not in RUN_STATUSES:
        raise ValueError(f"status de run inválido: {status}")
    timestamp = to_utc_iso(finished_at)
    with transaction(conn, f"não foi possível finalizar o run {run_id}"):
        conn.execute(
            "UPDATE run SET finished_at = ?, status = ?, stats = ?, updated_at = ? WHERE id = ?",
            (timestamp, status, json.dumps(stats, ensure_ascii=False), timestamp, run_id),
        )
