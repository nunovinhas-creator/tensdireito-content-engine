-- 0003_whatsapp_draft — fila local de revisão humana de rascunhos WhatsApp.
-- O estado UNVERIFIED é explícito até que uma pessoa indique verificação ao aprovar.
CREATE TABLE whatsapp_draft (
    id INTEGER NOT NULL PRIMARY KEY,
    raw_item_id INTEGER NOT NULL UNIQUE REFERENCES raw_item (id),
    editorial_score REAL NOT NULL,
    verification_status TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    approved_at TEXT
);

CREATE INDEX whatsapp_draft_status ON whatsapp_draft (status, id);
