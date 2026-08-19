-- ============================================================================
-- EHOS  knowledge_db/V001__init.sql
-- Service:      knowledge-service (+ rag-service)
-- Description:  Knowledge base schema: versioned knowledge documents, document
--               chunks with embedding metadata, and the access audit log.
-- Design:       DATABASE_DESIGN.md sections 8.2 (knowledge_db), 9 (event
--               outbox), 10 (cross-cutting standards), 2 (global conventions).
-- Shared objects (pgcrypto, pg_trgm, fn_append_history(), ehos_make_history(),
-- outbox_events) are applied FIRST by apply.py before this migration runs.
-- ============================================================================

BEGIN;

-- ============================================================================
-- knowledge_documents
-- ============================================================================
CREATE TABLE knowledge_documents (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_type     TEXT NOT NULL CHECK (doc_type IN ('GUIDELINE','POLICY','PROTOCOL','FORMULARY','TEXTBOOK','REGULATORY','PATIENT_ED')),
    title        TEXT NOT NULL,
    version      INT NOT NULL DEFAULT 1,
    status       TEXT NOT NULL DEFAULT 'PENDING'
                 CHECK (status IN ('PENDING','INDEXED','APPROVED','SUPERSEDED','REJECTED','RETIRED')),
    approved_by  UUID,
    source_uri   TEXT,
    content_ref  TEXT,
    chunk_count  INT,
    hash         TEXT,
    published_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by   UUID,
    updated_by   UUID,
    audit_reference TEXT,
    deleted_at   TIMESTAMPTZ,
    deleted_by   UUID,
    deletion_reason TEXT,
    UNIQUE (title, version)
);
CREATE INDEX idx_knowledge_documents_type ON knowledge_documents (doc_type, status);
SELECT ehos_make_history('knowledge_documents');

-- ============================================================================
-- document_chunks
-- ============================================================================
CREATE TABLE document_chunks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id  UUID NOT NULL REFERENCES knowledge_documents(id),
    chunk_index  INT NOT NULL,
    content      TEXT NOT NULL,
    embedding_id TEXT,
    token_count  INT,
    metadata     JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by   UUID,
    updated_by   UUID,
    version      INT NOT NULL DEFAULT 1,
    status       TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE')),
    audit_reference TEXT,
    deleted_at   TIMESTAMPTZ,
    deleted_by   UUID,
    deletion_reason TEXT,
    UNIQUE (document_id, chunk_index)
);
CREATE INDEX idx_document_chunks_document ON document_chunks (document_id);
SELECT ehos_make_history('document_chunks');

-- ============================================================================
-- knowledge_access_log — append-only access audit log (accessed_at only; no
-- updated_at, no soft delete). It is itself an audit log, so ehos_make_history
-- is intentionally skipped.
-- ============================================================================
CREATE TABLE knowledge_access_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES knowledge_documents(id),
    user_id     UUID,
    query       TEXT,
    accessed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    permitted   BOOLEAN NOT NULL
);
CREATE INDEX idx_knowledge_access_time ON knowledge_access_log (accessed_at DESC);

-- ============================================================================
-- Grants
-- ============================================================================
GRANT USAGE ON SCHEMA public TO ehos_knowledge_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_knowledge_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_knowledge_app;

COMMIT;