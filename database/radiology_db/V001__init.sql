-- ============================================================================
-- EHOS  radiology_db  V001__init.sql
-- radiology-service: imaging requests, DICOM studies/series, reports & versions.
-- Design: DATABASE_DESIGN.md sections 6.6, 2.5-2.7, 10; role 00_db_roles.sql.
-- Shared objects (pgcrypto, pg_trgm, fn_append_history(), ehos_make_history(),
-- outbox_events) are applied FIRST by apply.py; not included here.
-- Postgres 16+, lowercase snake_case.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- imaging_requests
-- ----------------------------------------------------------------------------
CREATE TABLE imaging_requests (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id         UUID NOT NULL,
    patient_snapshot   JSONB,
    encounter_id       UUID,
    ordering_doctor    UUID NOT NULL,
    modality           TEXT NOT NULL CHECK (modality IN ('XRAY','CT','MRI','US','MAMMO','FLUORO','PET','NM')),
    body_part          TEXT,
    clinical_indication TEXT,
    priority           TEXT NOT NULL DEFAULT 'ROUTINE' CHECK (priority IN ('ROUTINE','URGENT','STAT')),
    status             TEXT NOT NULL DEFAULT 'REQUESTED' CHECK (status IN ('REQUESTED','SCHEDULED','IN_PROGRESS','COMPLETED','REPORTED','CANCELLED')),
    ordered_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by         UUID,
    updated_by         UUID,
    version            INT NOT NULL DEFAULT 1,
    audit_reference    TEXT,
    deleted_at         TIMESTAMPTZ,
    deleted_by         UUID,
    deletion_reason    TEXT
);

CREATE INDEX idx_imaging_requests_patient ON imaging_requests (patient_id, ordered_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_imaging_requests_doctor ON imaging_requests (ordering_doctor);
CREATE INDEX idx_imaging_requests_encounter ON imaging_requests (encounter_id) WHERE encounter_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- studies — DICOM study metadata
-- ----------------------------------------------------------------------------
CREATE TABLE studies (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    imaging_request_id UUID REFERENCES imaging_requests(id),
    patient_id         UUID NOT NULL,
    study_instance_uid TEXT NOT NULL,
    accession_number   TEXT,
    modality           TEXT,
    started_at         TIMESTAMPTZ,
    ended_at           TIMESTAMPTZ,
    status             TEXT NOT NULL DEFAULT 'SCHEDULED' CHECK (status IN ('SCHEDULED','IN_PROGRESS','COMPLETED','ABORTED')),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by         UUID,
    updated_by         UUID,
    version            INT NOT NULL DEFAULT 1,
    audit_reference    TEXT,
    deleted_at         TIMESTAMPTZ,
    deleted_by         UUID,
    deletion_reason    TEXT
);

CREATE UNIQUE INDEX uq_studies_study_instance_uid ON studies (study_instance_uid) WHERE deleted_at IS NULL;
CREATE INDEX idx_studies_patient ON studies (patient_id);
CREATE INDEX idx_studies_request ON studies (imaging_request_id) WHERE imaging_request_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- series
-- ----------------------------------------------------------------------------
CREATE TABLE series (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    study_id           UUID NOT NULL REFERENCES studies(id),
    series_instance_uid TEXT NOT NULL,
    modality           TEXT,
    body_part          TEXT,
    images_count       INT,
    minio_bucket       TEXT,
    minio_prefix       TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by         UUID,
    updated_by         UUID,
    version            INT NOT NULL DEFAULT 1,
    audit_reference    TEXT,
    deleted_at         TIMESTAMPTZ,
    deleted_by         UUID,
    deletion_reason    TEXT
);

CREATE UNIQUE INDEX uq_series_series_instance_uid ON series (series_instance_uid) WHERE deleted_at IS NULL;
CREATE INDEX idx_series_study ON series (study_id);

-- ----------------------------------------------------------------------------
-- radiology_reports — findings + impression (RLS-protected)
-- ----------------------------------------------------------------------------
CREATE TABLE radiology_reports (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    study_id       UUID NOT NULL REFERENCES studies(id),
    patient_id     UUID NOT NULL,
    radiologist_id UUID,
    findings       TEXT,
    impression     TEXT,
    conclusion     TEXT,
    report_status  TEXT NOT NULL DEFAULT 'DRAFT' CHECK (report_status IN ('DRAFT','PENDING_REVIEW','FINAL','AMENDED','SIGNED')),
    dictated       BOOLEAN NOT NULL DEFAULT false,
    ai_assist      BOOLEAN NOT NULL DEFAULT false,
    ai_draft_ref   UUID,
    signed_by      UUID,
    signed_at      TIMESTAMPTZ,
    status         TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by     UUID,
    updated_by     UUID,
    version        INT NOT NULL DEFAULT 1,
    audit_reference TEXT,
    deleted_at     TIMESTAMPTZ,
    deleted_by     UUID,
    deletion_reason TEXT
);

CREATE INDEX idx_radiology_reports_study ON radiology_reports (study_id);
CREATE INDEX idx_radiology_reports_patient ON radiology_reports (patient_id);

-- RLS per design section 2.11 / 10
ALTER TABLE radiology_reports ENABLE ROW LEVEL SECURITY;

CREATE POLICY radiology_reports_select ON radiology_reports
    FOR SELECT TO ehos_radiology_app
    USING (deleted_at IS NULL);

CREATE POLICY radiology_reports_insert ON radiology_reports
    FOR INSERT TO ehos_radiology_app
    WITH CHECK (deleted_at IS NULL);

CREATE POLICY radiology_reports_update ON radiology_reports
    FOR UPDATE TO ehos_radiology_app
    USING (deleted_at IS NULL)
    WITH CHECK (deleted_at IS NULL);

CREATE POLICY radiology_reports_delete ON radiology_reports
    FOR DELETE TO ehos_radiology_app
    USING (deleted_at IS NULL);

-- ----------------------------------------------------------------------------
-- radiology_report_versions — application-level revision log
-- ----------------------------------------------------------------------------
CREATE TABLE radiology_report_versions (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id     UUID NOT NULL REFERENCES radiology_reports(id),
    version_no    INT NOT NULL,
    findings      TEXT,
    impression    TEXT,
    conclusion    TEXT,
    report_status TEXT,
    changed_by    UUID,
    changed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by    UUID,
    updated_by    UUID,
    version       INT NOT NULL DEFAULT 1,
    status        TEXT NOT NULL,
    audit_reference TEXT,
    deleted_at    TIMESTAMPTZ,
    deleted_by    UUID,
    deletion_reason TEXT
);

CREATE UNIQUE INDEX uq_radiology_report_versions_report ON radiology_report_versions (report_id, version_no);
CREATE INDEX idx_radiology_report_versions_report ON radiology_report_versions (report_id, version_no);

-- No ehos_make_history('radiology_report_versions'): this table IS the
-- version history for radiology_reports (mirrors clinical_note_versions §6.1);
-- the DB trigger history is owned by radiology_reports itself.

-- ----------------------------------------------------------------------------
-- history tables
-- ----------------------------------------------------------------------------
SELECT ehos_make_history('imaging_requests');
SELECT ehos_make_history('studies');
SELECT ehos_make_history('series');
SELECT ehos_make_history('radiology_reports');

-- ----------------------------------------------------------------------------
-- grants to application role
-- ----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO ehos_radiology_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_radiology_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_radiology_app;

COMMIT;