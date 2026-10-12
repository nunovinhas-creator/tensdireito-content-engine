-- 0004_candidate — registo persistente de candidatos (fase 2a; especificação das fases
-- 2–4, §1 e §2; DEC-064, DEC-068).
--
-- Um `candidate` é uma notícia, independentemente de quantas vezes e por que métodos foi
-- encontrada; cada descoberta fica em `candidate_discovery`. `source_document` mantém-se
-- como documento de cada captura (DEC-064). Excepção assumida à convenção de 0001–0003:
-- os valores enumerados têm `CHECK (coluna IN (...))`, que tem equivalente directo em
-- PostgreSQL (DEC-013); a validação no domínio mantém-se. Sem `ON DELETE` (DEC-029):
-- `tde prune` apaga pela ordem explícita das chaves. Datas em TEXT ISO 8601 UTC.
-- Uma migração aplicada nunca é editada: qualquer alteração é uma migração nova.

CREATE TABLE candidate_group (
    id INTEGER NOT NULL PRIMARY KEY,
    label TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE candidate (
    id INTEGER NOT NULL PRIMARY KEY,
    url_key TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    canonical_url TEXT,
    title TEXT NOT NULL,
    summary TEXT,
    source_id TEXT REFERENCES source_registry (id),
    source_tier TEXT NOT NULL CHECK (source_tier IN ('T1', 'T2', 'T3', 'T4')),
    published_at TEXT,
    published_at_source TEXT NOT NULL
        CHECK (published_at_source IN ('sitemap', 'feed', 'page', 'url', 'first_seen', 'none')),
    updated_at_source TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('alta', 'rever', 'baixa')),
    priority_reason TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN (
            'descoberto', 'fora_do_dia', 'arquivado', 'a_extrair', 'extraido', 'bloqueado',
            'a_classificar', 'classificado', 'descartado', 'pendente_revisao', 'agrupado',
            'rascunho', 'no_grupo', 'expirado'
        )
    ),
    attempts INTEGER NOT NULL CHECK (attempts >= 0),
    next_attempt_at TEXT,
    last_error TEXT,
    group_id INTEGER REFERENCES candidate_group (id),
    representative_document_id INTEGER REFERENCES source_document (id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE candidate_discovery (
    id INTEGER NOT NULL PRIMARY KEY,
    candidate_id INTEGER NOT NULL REFERENCES candidate (id),
    raw_item_id INTEGER NOT NULL REFERENCES raw_item (id),
    endpoint_id TEXT NOT NULL REFERENCES source_endpoint (id),
    method TEXT NOT NULL
        CHECK (method IN ('rss', 'news_sitemap', 'search', 'html_list', 'json_api', 'open_data')),
    first_seen_at TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    UNIQUE (candidate_id, endpoint_id)
);

CREATE TABLE candidate_transition (
    id INTEGER NOT NULL PRIMARY KEY,
    candidate_id INTEGER NOT NULL REFERENCES candidate (id),
    from_state TEXT,
    to_state TEXT NOT NULL,
    reason TEXT NOT NULL,
    run_id INTEGER REFERENCES run (id),
    at TEXT NOT NULL
);

-- Ligação do rascunho à notícia; nula nos rascunhos anteriores à 0004.
ALTER TABLE whatsapp_draft ADD COLUMN candidate_id INTEGER REFERENCES candidate (id);

-- Índices da §1.7: fila, janela do dia, grupos, cobertura por método e auditoria.
CREATE INDEX candidate_state_next_attempt ON candidate (state, next_attempt_at);
CREATE INDEX candidate_published_at ON candidate (published_at);
CREATE INDEX candidate_group_id ON candidate (group_id);
CREATE INDEX candidate_last_seen_at ON candidate (last_seen_at);
CREATE INDEX candidate_discovery_endpoint_seen ON candidate_discovery (endpoint_id, seen_at);
CREATE INDEX candidate_discovery_raw_item ON candidate_discovery (raw_item_id);
CREATE INDEX candidate_transition_candidate_at ON candidate_transition (candidate_id, at);
