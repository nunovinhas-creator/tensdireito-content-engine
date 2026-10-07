-- 0001_init — esquema inicial (M2.6; DEC-026; ROADMAP.md M2.6, secção "Esquema").
--
-- Só construções com equivalente directo em PostgreSQL (DEC-013): tipos TEXT,
-- INTEGER e REAL; PRIMARY KEY, FOREIGN KEY, UNIQUE e NOT NULL. Datas em TEXT
-- ISO 8601 UTC com fuso explícito e colunas json em TEXT com JSON válido, ambas
-- escritas pela camada storage. As enumerações são validadas pelos modelos de
-- domínio, não por CHECK. source_document fica para uma migração posterior.
-- Uma migração aplicada nunca é editada: qualquer alteração é uma migração nova.

-- Tabela técnica de controlo das migrações (DEC-026); não é entidade de negócio.
CREATE TABLE schema_migration (
    version INTEGER NOT NULL PRIMARY KEY,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

-- DATA_MODEL.md §2.9.
CREATE TABLE run (
    id INTEGER NOT NULL PRIMARY KEY,
    command TEXT,
    started_at TEXT,
    finished_at TEXT,
    status TEXT,
    stats TEXT,
    outcome TEXT,
    report_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- DATA_MODEL.md §2.1; espelho operacional de config/sources.yaml (DEC-027).
CREATE TABLE source_registry (
    id TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    tier TEXT NOT NULL,
    categories TEXT NOT NULL,
    domains TEXT NOT NULL,
    registry_status TEXT NOT NULL,
    validated_at TEXT,
    validated_by TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- DATA_MODEL.md §2.1; last_success_at e last_error só existem na base de dados (DEC-027).
CREATE TABLE source_endpoint (
    id TEXT NOT NULL PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES source_registry (id),
    endpoint_type TEXT NOT NULL,
    url TEXT,
    fetch TEXT,
    endpoint_status TEXT NOT NULL,
    validated_at TEXT,
    validated_by TEXT,
    last_success_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- DATA_MODEL.md §2.1. source_endpoint_id é nulo para pistas manuais; published_at_raw
-- é guardado tal como obtido (D13). Limitação conhecida: NULL em source_endpoint_id
-- não colide no UNIQUE (a tratar com tde add-manual).
CREATE TABLE raw_item (
    id INTEGER NOT NULL PRIMARY KEY,
    source_endpoint_id TEXT REFERENCES source_endpoint (id),
    url TEXT NOT NULL,
    external_id TEXT,
    title TEXT NOT NULL,
    raw_content TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    published_at_raw TEXT,
    content_hash TEXT NOT NULL,
    manual_note TEXT,
    created_in_run INTEGER REFERENCES run (id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (source_endpoint_id, url, content_hash)
);
