-- 0002_source_document — documentos normalizados (M2.11; DEC-026 (4), DEC-037 a DEC-041;
-- ROADMAP.md M2.11, secção "Esquema").
--
-- Cria só source_document; não altera nenhuma tabela da 0001. Mesmas regras de
-- portabilidade da 0001 (DEC-013): tipos TEXT e INTEGER; PRIMARY KEY, FOREIGN KEY,
-- UNIQUE, NOT NULL e CREATE INDEX simples. As enumerações (source_tier, status) são
-- validadas pelo domínio antes da escrita, não por CHECK. Datas em TEXT ISO 8601 UTC
-- com fuso explícito, escritas pela camada storage.
--
-- canonical_url é sempre nulo enquanto D12 estiver OPEN (DEC-037); language é nulo
-- quando desconhecida (DEC-038); document_kind é nulo quando não determinado (DEC-039);
-- text e text_hash são nulos sem texto útil (DEC-040). As colunas da etapa CLASSIFY
-- (proposed_*, relevance_flag, classified_by) entram numa migração dessa unidade.
-- Uma migração aplicada nunca é editada: qualquer alteração é uma migração nova.

-- DATA_MODEL.md §2.1.
CREATE TABLE source_document (
    id INTEGER NOT NULL PRIMARY KEY,
    raw_item_id INTEGER NOT NULL REFERENCES raw_item (id),
    source_id TEXT REFERENCES source_registry (id),
    canonical_url TEXT,
    title TEXT NOT NULL,
    text TEXT,
    language TEXT,
    published_at TEXT,
    source_tier TEXT NOT NULL,
    document_kind TEXT,
    text_hash TEXT,
    duplicate_of INTEGER REFERENCES source_document (id),
    status TEXT NOT NULL,
    created_in_run INTEGER NOT NULL REFERENCES run (id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (raw_item_id)
);

-- Procura do representante por text_hash (DEC-041 (12)); não único.
CREATE INDEX source_document_text_hash ON source_document (text_hash);
