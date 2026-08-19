-- ============================================================================
-- EHOS  bed_db  V001__init.sql
-- bed-service: wards, beds, occupancy requests & transfers.
-- Design: DATABASE_DESIGN.md sections 6.9, 2.5-2.7, 10; role 00_db_roles.sql.
-- Shared objects (pgcrypto, pg_trgm, fn_append_history(), ehos_make_history(),
-- outbox_events) are applied FIRST by apply.py; not included here.
-- Postgres 16+, lowercase snake_case.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- wards
-- ----------------------------------------------------------------------------
CREATE TABLE wards (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code          TEXT NOT NULL,
    name          TEXT NOT NULL,
    floor         TEXT,
    department_id UUID,
    ward_type     TEXT CHECK (ward_type IN ('GENERAL','ICU','CCU','PAEDS','MATERNITY','ISOLATION','SURGICAL')),
    beds_planned  INT NOT NULL,
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

CREATE UNIQUE INDEX uq_wards_code ON wards (code) WHERE deleted_at IS NULL;
CREATE INDEX idx_wards_department ON wards (department_id) WHERE department_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- beds
-- ----------------------------------------------------------------------------
CREATE TABLE beds (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ward_id         UUID NOT NULL REFERENCES wards(id),
    bed_number      TEXT NOT NULL,
    bed_type        TEXT NOT NULL DEFAULT 'GENERAL' CHECK (bed_type IN ('GENERAL','ICU','HDU','ISOLATION','PEDIATRIC','MATERNITY')),
    status          TEXT NOT NULL DEFAULT 'AVAILABLE' CHECK (status IN ('AVAILABLE','OCCUPIED','RESERVED','CLEANING','MAINTENANCE','OUT_OF_SERVICE')),
    current_patient UUID,
    occupant_since  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID,
    updated_by      UUID,
    version         INT NOT NULL DEFAULT 1,
    audit_reference TEXT,
    deleted_at      TIMESTAMPTZ,
    deleted_by      UUID,
    deletion_reason TEXT
);

CREATE UNIQUE INDEX uq_beds_ward_number ON beds (ward_id, bed_number) WHERE deleted_at IS NULL;
CREATE INDEX idx_beds_status ON beds (ward_id, status, bed_type) WHERE deleted_at IS NULL;
CREATE INDEX idx_beds_current_patient ON beds (current_patient) WHERE current_patient IS NOT NULL;

-- ----------------------------------------------------------------------------
-- bed_requests
-- ----------------------------------------------------------------------------
CREATE TABLE bed_requests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id      UUID NOT NULL,
    encounter_id    UUID,
    request_type    TEXT NOT NULL CHECK (request_type IN ('ADMISSION','TRANSFER','INTERNAL')),
    ward_preference UUID,
    bed_type        TEXT,
    priority        TEXT NOT NULL DEFAULT 'ROUTINE' CHECK (priority IN ('ROUTINE','URGENT','EMERGENCY')),
    requested_by    UUID NOT NULL,
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    status          TEXT NOT NULL DEFAULT 'REQUESTED' CHECK (status IN ('REQUESTED','ASSIGNED','AWAITING','CANCELLED','COMPLETED')),
    assigned_bed    UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID,
    updated_by      UUID,
    version         INT NOT NULL DEFAULT 1,
    audit_reference TEXT,
    deleted_at      TIMESTAMPTZ,
    deleted_by      UUID,
    deletion_reason TEXT
);

CREATE INDEX idx_bed_requests_patient ON bed_requests (patient_id);
CREATE INDEX idx_bed_requests_encounter ON bed_requests (encounter_id) WHERE encounter_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- bed_transfers
-- ----------------------------------------------------------------------------
CREATE TABLE bed_transfers (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id     UUID NOT NULL,
    from_bed_id    UUID REFERENCES beds(id),
    to_bed_id      UUID NOT NULL REFERENCES beds(id),
    reason         TEXT,
    requested_by   UUID,
    transferred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by     UUID,
    updated_by     UUID,
    version        INT NOT NULL DEFAULT 1,
    status         TEXT NOT NULL,
    audit_reference TEXT,
    deleted_at     TIMESTAMPTZ,
    deleted_by     UUID,
    deletion_reason TEXT
);

CREATE INDEX idx_bed_transfers_patient ON bed_transfers (patient_id);
CREATE INDEX idx_bed_transfers_from ON bed_transfers (from_bed_id);
CREATE INDEX idx_bed_transfers_to ON bed_transfers (to_bed_id);

-- ----------------------------------------------------------------------------
-- history tables
-- ----------------------------------------------------------------------------
SELECT ehos_make_history('wards');
SELECT ehos_make_history('beds');
SELECT ehos_make_history('bed_requests');
SELECT ehos_make_history('bed_transfers');

-- ----------------------------------------------------------------------------
-- grants to application role
-- ----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO ehos_bed_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_bed_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_bed_app;

COMMIT;