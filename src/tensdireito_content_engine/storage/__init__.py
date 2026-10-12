"""Camada de persistência SQLite (ARCHITECTURE.md §5; ROADMAP.md M2.6; DEC-013, DEC-026).

Todo o SQL e todo o uso de `sqlite3` vivem neste pacote. `domain/`, `normalize/` e
`sources/` não o importam; a CLI chama estas funções, sem SQL. No M2.6 existem só a
ligação, o executor de migrações e `tde init`; o M2.7 acrescenta a sincronização de
`source_registry` e `source_endpoint` (`tde sources sync`); o M2.8 acrescenta os
repositórios de `run`, de `raw_item` e do estado operacional de `source_endpoint`
(`tde collect`); o M2.11 acrescenta a migração `0002`, o repositório de
`source_document` e a leitura dos `raw_item` pendentes (`tde normalize`). Os restantes
repositórios por entidade chegam com as unidades que os consomem.
"""

from tensdireito_content_engine.storage.database import (
    DB_PATH_ENV,
    DEFAULT_DB_PATH,
    connect,
    resolve_db_path,
    to_utc_iso,
    transaction,
)
from tensdireito_content_engine.storage.drafts import (
    DraftIssueData,
    WhatsAppDraft,
    approve_draft,
    create_pending_draft,
    export_approved_drafts,
    list_drafts,
    list_unverified_drafts_for_issues,
    persist_pending_drafts,
)
from tensdireito_content_engine.storage.endpoints import (
    active_endpoints,
    record_endpoint_failure,
    source_exists,
)
from tensdireito_content_engine.storage.errors import StorageError
from tensdireito_content_engine.storage.init import InitResult, init_database
from tensdireito_content_engine.storage.interfaces import Connection
from tensdireito_content_engine.storage.migrator import Migration, load_migrations, migrate
from tensdireito_content_engine.storage.raw_items import (
    SavedItems,
    StoredRawItem,
    list_raw_items,
    prune_raw_items,
    save_endpoint_items,
)
from tensdireito_content_engine.storage.runs import (
    RUN_STATUSES,
    finish_run,
    previous_run_stats,
    start_run,
)
from tensdireito_content_engine.storage.schema import open_existing_database
from tensdireito_content_engine.storage.source_documents import (
    PendingRawItem,
    insert_source_document,
    pending_raw_items,
)
from tensdireito_content_engine.storage.source_sync import (
    SourceSyncError,
    SyncCounts,
    SyncResult,
    sync_sources,
)

__all__ = [
    "prune_raw_items",
    "DB_PATH_ENV",
    "DEFAULT_DB_PATH",
    "RUN_STATUSES",
    "Connection",
    "DraftIssueData",
    "WhatsAppDraft",
    "InitResult",
    "Migration",
    "PendingRawItem",
    "SavedItems",
    "SourceSyncError",
    "StorageError",
    "StoredRawItem",
    "SyncCounts",
    "SyncResult",
    "active_endpoints",
    "approve_draft",
    "connect",
    "create_pending_draft",
    "export_approved_drafts",
    "finish_run",
    "previous_run_stats",
    "init_database",
    "insert_source_document",
    "load_migrations",
    "list_raw_items",
    "list_drafts",
    "list_unverified_drafts_for_issues",
    "migrate",
    "open_existing_database",
    "pending_raw_items",
    "persist_pending_drafts",
    "record_endpoint_failure",
    "resolve_db_path",
    "save_endpoint_items",
    "source_exists",
    "start_run",
    "sync_sources",
    "to_utc_iso",
    "transaction",
]
