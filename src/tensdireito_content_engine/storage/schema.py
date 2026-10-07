"""Pré-condições de base existente e esquema conforme (ROADMAP.md M2.7 e M2.8; DEC-028).

Partilhadas pelos comandos que exigem uma base criada por `tde init` (`tde sources sync`
e `tde collect`): nenhum deles cria a base de dados nem aplica migrações.
"""

import sqlite3
from pathlib import Path

from tensdireito_content_engine.storage.database import connect
from tensdireito_content_engine.storage.errors import StorageError
from tensdireito_content_engine.storage.migrator import (
    applied_migrations,
    load_migrations,
    pending_migrations,
)

INIT_HINT = "execute `tde init`"


def require_database(path: Path) -> None:
    """Verificado antes de `connect()`, que criaria o ficheiro e o directório pai."""
    if not Path(path).exists():
        raise StorageError(f"a base de dados não existe; {INIT_HINT} para a criar")


def check_schema(conn: sqlite3.Connection) -> None:
    """O esquema tem de estar conforme às migrações do código; nada é migrado."""
    try:
        pending = pending_migrations(applied_migrations(conn), load_migrations())
    except StorageError as exc:
        raise StorageError(f"esquema não conforme: {exc}; {INIT_HINT}") from exc
    if pending:
        names = ", ".join(migration.name for migration in pending)
        raise StorageError(f"esquema não conforme: migrações pendentes: {names}; {INIT_HINT}")


def open_existing_database(path: Path) -> sqlite3.Connection:
    """Abre uma base existente com esquema conforme; qualquer falha pede `tde init`."""
    require_database(path)
    try:
        conn = connect(Path(path))
    except StorageError as exc:
        raise StorageError(f"esquema não conforme: {exc}; {INIT_HINT}") from exc
    try:
        check_schema(conn)
    except BaseException:
        conn.close()
        raise
    return conn
