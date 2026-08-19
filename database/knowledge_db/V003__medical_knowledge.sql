-- ============================================================================
-- EHOS  knowledge_db/V003__medical_knowledge.sql
-- Service:      knowledge-service (RAG)
-- Description:  Medical Knowledge Base additions: extend doc_type with the
--               JOURNAL corpus (medical journals), and add loader provenance
--               columns on knowledge_documents (source_format, ingestion_ref)
--               so every ingested document records how and from where it came.
-- Design:       MEDICAL_KNOWLEDGE_BASE.md sections 3, 4, 5.
-- Applies after V001__init.sql and V002__rag_corpora.sql.
-- ============================================================================

BEGIN;

-- ============================================================================
-- Extend knowledge_documents.doc_type (drop + recreate constraint)
--   + JOURNAL : medical journal articles
-- ============================================================================
ALTER TABLE knowledge_documents DROP CONSTRAINT knowledge_documents_doc_type_check;
ALTER TABLE knowledge_documents
    ADD CONSTRAINT knowledge_documents_doc_type_check
    CHECK (doc_type IN ('GUIDELINE','POLICY','PROTOCOL','FORMULARY','TEXTBOOK','REGULATORY',
                        'PATIENT_ED','MEDICATION','LAB_REFERENCE','JOURNAL'));

-- ============================================================================
-- Loader provenance on knowledge_documents
--   source_format : PDF | DOCX | SOP | FORMULARY | TEXTBOOK | JOURNAL | MARKDOWN | TEXT
--   ingestion_ref : file URI/locator the document was ingested from
-- ============================================================================
ALTER TABLE knowledge_documents
    ADD COLUMN source_format TEXT,
    ADD COLUMN ingestion_ref TEXT;

-- ============================================================================
-- Grants (new/changed objects; ALL TABLES grant from V001/V002 covers them)
-- ============================================================================
GRANT USAGE ON SCHEMA public TO ehos_knowledge_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_knowledge_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_knowledge_app;

COMMIT;