"""Camada de persistência SQLite (ARCHITECTURE.md §5; ROADMAP.md M2.6; DEC-013, DEC-026).

Todo o SQL e todo o uso de `sqlite3` vivem neste pacote. `domain/`, `normalize/` e
`sources/` não o importam; a CLI chama estas funções, sem SQL. No M2.6 existem só a
ligação, o executor de migrações e `tde init`; o M2.7 acrescenta a sincronização de
`source_registry` e `source_endpoint` (`tde sources sync`). Os restantes repositórios
por entidade chegam com as unidades que os consomem.
"""

from tensdireito_content_engine.storage.database import (
    DB_PATH_ENV,
    DEFAULT_DB_PATH,
    connect,
    resolve_db_path,
    to_utc_iso,
)
from tensdireito_content_engine.storage.errors import StorageError
from tensdireito_content_engine.storage.init import InitResult, init_database
from tensdireito_content_engine.storage.migrator import Migration, load_migrations, migrate
from tensdireito_content_engine.storage.source_sync import (
    SourceSyncError,
    SyncCounts,
    SyncResult,
    sync_sources,
)

__all__ = [
    "DB_PATH_ENV",
    "DEFAULT_DB_PATH",
    "InitResult",
    "Migration",
    "SourceSyncError",
    "StorageError",
    "SyncCounts",
    "SyncResult",
    "connect",
    "init_database",
    "load_migrations",
    "migrate",
    "resolve_db_path",
    "sync_sources",
    "to_utc_iso",
]
