-- ============================================================================
-- EHOS  documentation_db  V001__init.sql
-- clinical-documentation-service: clinical notes, versions, templates.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- clinical_notes — clinical documentation notes with version history
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clinical_notes (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id     UUID NOT NULL,
    encounter_id   UUID,
    author_id      UUID NOT NULL,
    note_type      VARCHAR NOT NULL,
    title          VARCHAR,
    content        TEXT,
    structured_data JSON,
    status         VARCHAR NOT NULL DEFAULT 'DRAFT',
    signed_by      UUID,
    signed_at      TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by     UUID,
    updated_by     UUID,
    model_version  INTEGER NOT NULL DEFAULT 1,
    audit_reference VARCHAR,
    deleted_at     TIMESTAMPTZ,
    deleted_by     UUID,
    deletion_reason TEXT,
    CONSTRAINT ck_note_type CHECK (note_type IN ('SOAP','PROGRESS','DISCHARGE','PROCEDURE','CONSULTATION','H&P','NURSING','CONSENT')),
    CONSTRAINT ck_note_status CHECK (status IN ('DRAFT','FINAL','AMENDED','CANCELLED'))
);

CREATE INDEX IF NOT EXISTS idx_notes_patient ON clinical_notes(patient_id, created_at);
CREATE INDEX IF NOT EXISTS idx_notes_encounter ON clinical_notes(encounter_id);
CREATE INDEX IF NOT EXISTS idx_notes_author ON clinical_notes(author_id);

-- ----------------------------------------------------------------------------
-- note_versions — immutable snapshots per edit
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS note_versions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    note_id        UUID NOT NULL REFERENCES clinical_notes(id),
    version_number INTEGER NOT NULL,
    content        TEXT,
    structured_data JSON,
    changed_by     UUID NOT NULL,
    change_summary TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by     UUID,
    updated_by     UUID,
    model_version  INTEGER NOT NULL DEFAULT 1,
    status         VARCHAR NOT NULL,
    audit_reference VARCHAR,
    deleted_at     TIMESTAMPTZ,
    deleted_by     UUID,
    deletion_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_versions_note ON note_versions(note_id);

-- ----------------------------------------------------------------------------
-- templates — reusable documentation templates
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS templates (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name           VARCHAR NOT NULL,
    note_type      VARCHAR NOT NULL,
    content        TEXT,
    structured_schema JSON,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by     UUID,
    updated_by     UUID,
    model_version  INTEGER NOT NULL DEFAULT 1,
    status         VARCHAR NOT NULL,
    audit_reference VARCHAR,
    deleted_at     TIMESTAMPTZ,
    deleted_by     UUID,
    deletion_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_templates_type ON templates(note_type);

-- ----------------------------------------------------------------------------
-- history tables
-- ----------------------------------------------------------------------------
SELECT ehos_make_history('clinical_notes');
SELECT ehos_make_history('note_versions');
SELECT ehos_make_history('templates');

-- ----------------------------------------------------------------------------
-- grants
-- ----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO ehos_documentation_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_documentation_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_documentation_app;

COMMIT;