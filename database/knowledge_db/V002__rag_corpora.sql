-- ============================================================================
-- EHOS  knowledge_db/V002__rag_corpora.sql
-- Service:      knowledge-service (RAG)
-- Description:  RAG additions for HospitalGPT: extend doc_type with the
--               medication and laboratory-reference corpora, a ppgvector-ready
--               embedding column on document_chunks, and a corpus catalog used
--               to seed the Clinical Guidelines / Hospital Policies / Medication
--               Database / Laboratory Reference knowledge sets.
-- Design:       DATABASE_DESIGN.md section 8.2 (knowledge_db),
--               HOSPITALGPT_ARCHITECTURE.md sections 3, 7.
-- Applies after V001__init.sql (roles and shared objects already exist).
-- Embeddings are stored as JSONB (float array) for portability (in-memory
-- SQLite tests and Postgres); cosine similarity is computed in the VectorStore.
-- ============================================================================

BEGIN;

-- ============================================================================
-- Extend knowledge_documents.doc_type (drop + recreate constraint)
-- ============================================================================
ALTER TABLE knowledge_documents DROP CONSTRAINT knowledge_documents_doc_type_check;
ALTER TABLE knowledge_documents
    ADD CONSTRAINT knowledge_documents_doc_type_check
    CHECK (doc_type IN ('GUIDELINE','POLICY','PROTOCOL','FORMULARY','TEXTBOOK','REGULATORY',
                        'PATIENT_ED','MEDICATION','LAB_REFERENCE'));

-- ============================================================================
-- Vector storage on document_chunks
--   embedding   : JSONB float array (dimensions from the embedding model)
--   embedding_model / embedding_dim : provenance for re-embedding on model change
-- ============================================================================
ALTER TABLE document_chunks
    ADD COLUMN embedding JSONB,
    ADD COLUMN embedding_model TEXT,
    ADD COLUMN embedding_dim INT;

-- ============================================================================
-- knowledge_corpora — catalog of named RAG corpora (enables doc-type mapping)
-- ============================================================================
CREATE TABLE knowledge_corpora (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key           TEXT NOT NULL,
    name          TEXT NOT NULL,
    description   TEXT,
    doc_type      TEXT,
    is_seeded     BOOLEAN NOT NULL DEFAULT false,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by    UUID,
    updated_by    UUID,
    version       INT NOT NULL DEFAULT 1,
    status        TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE')),
    audit_reference TEXT,
    deleted_at    TIMESTAMPTZ,
    deleted_by    UUID,
    deletion_reason TEXT,
    UNIQUE (key)
);
CREATE INDEX idx_knowledge_corpora_type ON knowledge_corpora (doc_type) WHERE deleted_at IS NULL;
SELECT ehos_make_history('knowledge_corpora');

-- ============================================================================
-- Search index: pg_trgm GIN over chunk content (element similar search)
-- ============================================================================
CREATE INDEX idx_document_chunks_content_trgm ON document_chunks
    USING GIN (content gin_trgm_ops);

-- ============================================================================
-- Grants (new/changed objects; ALL TABLES in V001 only covered then-existing tables)
-- ============================================================================
GRANT USAGE ON SCHEMA public TO ehos_knowledge_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_knowledge_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_knowledge_app;

COMMIT;