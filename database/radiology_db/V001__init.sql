-- ============================================================================
-- EHOS  radiology_db  V001__init.sql
-- radiology-service: modality catalog, orders, studies, reports.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- modalities — imaging modality catalog
-- ----------------------------------------------------------------------------
CREATE TABLE modalities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code            TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID,
    updated_by      UUID,
    version         INT NOT NULL DEFAULT 1,
    status          TEXT NOT NULL,
    audit_reference TEXT,
    deleted_at      TIMESTAMPTZ,
    deleted_by      UUID,
    deletion_reason TEXT
);

CREATE UNIQUE INDEX uq_modalities_code ON modalities (code) WHERE deleted_at IS NULL;

-- ----------------------------------------------------------------------------
-- radiology_orders — order header
-- ----------------------------------------------------------------------------
CREATE TABLE radiology_orders (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id           UUID NOT NULL,
    patient_snapshot     JSONB,
    encounter_id         UUID,
    ordering_doctor      UUID NOT NULL,
    modality_code        TEXT NOT NULL,
    body_region          TEXT NOT NULL,
    clinical_indication  TEXT,
    priority             TEXT NOT NULL DEFAULT 'ROUTINE' CHECK (priority IN ('ROUTINE','URGENT','STAT')),
    contrast             BOOLEAN NOT NULL DEFAULT false,
    ordered_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    scheduled_at         TIMESTAMPTZ,
    status               TEXT NOT NULL DEFAULT 'ORDERED' CHECK (status IN ('ORDERED','SCHEDULED','PERFORMING','COMPLETED','CANCELLED')),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by           UUID,
    updated_by           UUID,
    version              INT NOT NULL DEFAULT 1,
    audit_reference      TEXT,
    deleted_at           TIMESTAMPTZ,
    deleted_by           UUID,
    deletion_reason      TEXT
);

CREATE INDEX idx_rad_orders_patient ON radiology_orders (patient_id, ordered_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_rad_orders_doctor ON radiology_orders (ordering_doctor);
CREATE INDEX idx_rad_orders_modality ON radiology_orders (modality_code);

-- ----------------------------------------------------------------------------
-- studies — imaging studies performed
-- ----------------------------------------------------------------------------
CREATE TABLE studies (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id           UUID NOT NULL REFERENCES radiology_orders(id),
    patient_id         UUID NOT NULL,
    modality_code      TEXT NOT NULL,
    body_region        TEXT NOT NULL,
    study_instance_uid TEXT,
    accession_number   TEXT,
    performed_by       UUID,
    performed_at       TIMESTAMPTZ,
    started_at         TIMESTAMPTZ,
    completed_at       TIMESTAMPTZ,
    status             TEXT NOT NULL DEFAULT 'SCHEDULED' CHECK (status IN ('SCHEDULED','IN_PROGRESS','COMPLETED','CANCELLED')),
    technician_notes   TEXT,
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

CREATE UNIQUE INDEX uq_studies_instance_uid ON studies (study_instance_uid) WHERE study_instance_uid IS NOT NULL;
CREATE INDEX idx_studies_order ON studies (order_id);
CREATE INDEX idx_studies_patient ON studies (patient_id);

-- ----------------------------------------------------------------------------
-- radiology_reports
-- ----------------------------------------------------------------------------
CREATE TABLE radiology_reports (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id           UUID NOT NULL REFERENCES radiology_orders(id),
    patient_id         UUID NOT NULL,
    study_id           UUID REFERENCES studies(id),
    findings           TEXT,
    impression         TEXT,
    recommendation     TEXT,
    structured_report  JSONB,
    status             TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','PRELIMINARY','FINAL','AMENDED','CANCELLED')),
    signed_by          UUID,
    signed_at          TIMESTAMPTZ,
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

CREATE INDEX idx_rad_reports_order ON radiology_reports (order_id);
CREATE INDEX idx_rad_reports_patient ON radiology_reports (patient_id);
CREATE INDEX idx_rad_reports_study ON radiology_reports (study_id) WHERE study_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- history tables
-- ----------------------------------------------------------------------------
SELECT ehos_make_history('modalities');
SELECT ehos_make_history('radiology_orders');
SELECT ehos_make_history('studies');
SELECT ehos_make_history('radiology_reports');

-- ----------------------------------------------------------------------------
-- grants to application role
-- ----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO ehos_radiology_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_radiology_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_radiology_app;

COMMIT;
