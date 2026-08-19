-- ============================================================================
-- EHOS  documentation_db/V001__init.sql
-- Service:      clinical-documentation-service
-- Description:  Document registry: reusable templates with variable schema,
--               generated documents with an approval/signature lifecycle, and
--               immutable application-level document versions.
-- Design refs:  DATABASE_DESIGN.md sections 2.5, 2.6, 2.7, 2.8, 6.2, 9, 10
-- NOTE: Shared objects (pgcrypto, pg_trgm, fn_append_history(),
--       ehos_make_history(), outbox_events) are applied BEFORE this file by
--       apply.py and are NOT re-created here.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- document_templates
-- ----------------------------------------------------------------------------
CREATE TABLE document_templates (
    id            uuid primary key default gen_random_uuid(),
    code          text not null,
    doc_type      text not null check (doc_type in ('CONSENT','REPORT','CERTIFICATE','DISCHARGE_SUMMARY','REFERRAL','LETTER','AI_DRAFT')),
    title         text not null,
    body_template text not null,
    vars_schema   jsonb,
    is_active     boolean not null default true,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    created_by    uuid,
    updated_by    uuid,
    version       int not null default 1,
    status        text not null default 'ACTIVE',
    audit_reference text,
    deleted_at    timestamptz,
    deleted_by    uuid,
    deletion_reason text
);

CREATE UNIQUE INDEX uq_document_templates_code ON document_templates (code) WHERE deleted_at IS NULL;

SELECT ehos_make_history('document_templates');

-- ----------------------------------------------------------------------------
-- documents
-- ----------------------------------------------------------------------------
CREATE TABLE documents (
    id          uuid primary key default gen_random_uuid(),
    patient_id  uuid,                       -- cross-db ref to patient-service (no FK)
    encounter_id uuid,                      -- cross-db ref to ehr-service (no FK)
    doc_type    text not null,
    template_id uuid references document_templates(id),
    title       text,
    body        text,
    author_id   uuid not null,              -- cross-db ref to hr/identity (no FK)
    approver_id uuid,
    approved_at timestamptz,
    signer_id   uuid,
    signed_at   timestamptz,
    ai_draft_ref uuid,
    content_hash text,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    created_by  uuid,
    updated_by  uuid,
    version     int not null default 1,
    status      text not null default 'DRAFT' check (status in ('DRAFT','PENDING_APPROVAL','APPROVED','SIGNED','PUBLISHED','ARCHIVED','REJECTED')),
    audit_reference text,
    deleted_at  timestamptz,
    deleted_by  uuid,
    deletion_reason text
);

CREATE INDEX idx_documents_patient ON documents (patient_id);
CREATE INDEX idx_documents_type_status ON documents (doc_type, status);
CREATE INDEX idx_documents_template ON documents (template_id);

SELECT ehos_make_history('documents');

-- ----------------------------------------------------------------------------
-- document_versions
-- NOTE: application-level version table (design 6.2); already the version
--       artifact and carries no common-block columns, so no ehos_make_history().
-- ----------------------------------------------------------------------------
CREATE TABLE document_versions (
    id          uuid primary key default gen_random_uuid(),
    document_id uuid not null references documents(id),
    version_no  int not null,
    body        text not null,
    status      text,
    changed_by  uuid,
    changed_at  timestamptz not null default now(),
    constraint uq_document_versions_document_version unique (document_id, version_no)
);

CREATE INDEX idx_document_versions_document ON document_versions (document_id);

GRANT USAGE ON SCHEMA public TO ehos_documentation_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_documentation_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_documentation_app;

COMMIT;