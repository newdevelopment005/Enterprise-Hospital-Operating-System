-- ============================================================================
-- EHOS  emergency_db  V001__init.sql
-- emergency-service: ED registration & triage flow.
-- Design: DATABASE_DESIGN.md sections 6.7, 2.5-2.7, 10; role 00_db_roles.sql.
-- Shared objects (pgcrypto, pg_trgm, fn_append_history(), ehos_make_history(),
-- outbox_events) are applied FIRST by apply.py; not included here.
-- Postgres 16+, lowercase snake_case.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- emergency_registrations
-- ----------------------------------------------------------------------------
CREATE TABLE emergency_registrations (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id       UUID,
    patient_snapshot JSONB,
    registration_no  TEXT NOT NULL,
    arrival_mode     TEXT CHECK (arrival_mode IN ('WALK_IN','AMBULANCE','TRANSFER','POLICE')),
    complaint        TEXT,
    registered_by    UUID NOT NULL,
    registered_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    status           TEXT NOT NULL DEFAULT 'REGISTERED' CHECK (status IN ('REGISTERED','TRIAGED','IN_TREATMENT','ADMITTED','DISCHARGED','TRANSFERRED','DOA')),
    disposition      TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    version          INT NOT NULL DEFAULT 1,
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason  TEXT
);

CREATE UNIQUE INDEX uq_emergency_registrations_no ON emergency_registrations (registration_no);
CREATE INDEX idx_emergency_active ON emergency_registrations (status) WHERE status IN ('REGISTERED','TRIAGED','IN_TREATMENT');
CREATE INDEX idx_emergency_registrations_patient ON emergency_registrations (patient_id) WHERE patient_id IS NOT NULL;
CREATE INDEX idx_emergency_registrations_registered_by ON emergency_registrations (registered_by);

-- ----------------------------------------------------------------------------
-- triage_assessments
-- ----------------------------------------------------------------------------
CREATE TABLE triage_assessments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    registration_id     UUID NOT NULL REFERENCES emergency_registrations(id),
    patient_id          UUID,
    triage_level        INT NOT NULL CHECK (triage_level BETWEEN 1 AND 5),
    vitals              JSONB,
    chief_complaint     TEXT,
    triaged_by          UUID NOT NULL,
    triaged_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    escalation_notified BOOLEAN NOT NULL DEFAULT false,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by          UUID,
    updated_by          UUID,
    version             INT NOT NULL DEFAULT 1,
    audit_reference     TEXT,
    deleted_at          TIMESTAMPTZ,
    deleted_by          UUID,
    deletion_reason     TEXT
);

CREATE INDEX idx_triage_registration ON triage_assessments (registration_id);
CREATE INDEX idx_triage_patient ON triage_assessments (patient_id) WHERE patient_id IS NOT NULL;
CREATE INDEX idx_triage_triaged_by ON triage_assessments (triaged_by);

-- ----------------------------------------------------------------------------
-- history tables
-- ----------------------------------------------------------------------------
SELECT ehos_make_history('emergency_registrations');
SELECT ehos_make_history('triage_assessments');

-- ----------------------------------------------------------------------------
-- grants to application role
-- ----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO ehos_emergency_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_emergency_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_emergency_app;

COMMIT;