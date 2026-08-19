-- ============================================================================
-- EHOS  surgery_db  V001__init.sql
-- surgery-service: surgical scheduling, team, perioperative records & checklists.
-- Design: DATABASE_DESIGN.md sections 6.8, 2.5-2.7, 10; role 00_db_roles.sql.
-- Shared objects (pgcrypto, pg_trgm, fn_append_history(), ehos_make_history(),
-- outbox_events) are applied FIRST by apply.py; not included here.
-- Postgres 16+, lowercase snake_case.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- surgeries
-- ----------------------------------------------------------------------------
CREATE TABLE surgeries (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id         UUID NOT NULL,
    surgeon_id         UUID NOT NULL,
    anesthesiologist_id UUID,
    encounter_id       UUID,
    theatre_id         UUID,
    procedure_code     TEXT,
    procedure_name     TEXT NOT NULL,
    complexity         TEXT CHECK (complexity IN ('MINOR','INTERMEDIATE','MAJOR','COMPLEX')),
    planned_start      TIMESTAMPTZ NOT NULL,
    planned_end        TIMESTAMPTZ,
    actual_start       TIMESTAMPTZ,
    actual_end         TIMESTAMPTZ,
    status             TEXT NOT NULL DEFAULT 'SCHEDULED' CHECK (status IN ('SCHEDULED','ON_HOLD','PREOP','IN_PROGRESS','SUTURE','IN_RECOVERY','COMPLETED','CANCELLED')),
    cancellation_reason TEXT,
    urgency            TEXT NOT NULL DEFAULT 'ELECTIVE' CHECK (urgency IN ('ELECTIVE','URGENT','EMERGENCY')),
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

CREATE INDEX idx_surgeries_surgeon_time ON surgeries (surgeon_id, planned_start) WHERE deleted_at IS NULL;
CREATE INDEX idx_surgeries_date ON surgeries (planned_start) WHERE deleted_at IS NULL;
CREATE INDEX idx_surgeries_patient ON surgeries (patient_id);
CREATE INDEX idx_surgeries_encounter ON surgeries (encounter_id) WHERE encounter_id IS NOT NULL;
CREATE INDEX idx_surgeries_theatre ON surgeries (theatre_id) WHERE theatre_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- surgery_team_members
-- ----------------------------------------------------------------------------
CREATE TABLE surgery_team_members (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    surgery_id  UUID NOT NULL REFERENCES surgeries(id),
    member_id   UUID NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('SURGEON','ASSISTANT','ANESTHESIOLOGIST','NURSE','SCRUB','CIRCULATING')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by  UUID,
    updated_by  UUID,
    version     INT NOT NULL DEFAULT 1,
    status      TEXT NOT NULL,
    audit_reference TEXT,
    deleted_at  TIMESTAMPTZ,
    deleted_by  UUID,
    deletion_reason TEXT
);

CREATE INDEX idx_surgery_team_surgery ON surgery_team_members (surgery_id);
CREATE INDEX idx_surgery_team_member ON surgery_team_members (member_id);

-- ----------------------------------------------------------------------------
-- perioperative_records
-- ----------------------------------------------------------------------------
CREATE TABLE perioperative_records (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    surgery_id  UUID NOT NULL REFERENCES surgeries(id),
    stage       TEXT NOT NULL,
    findings    TEXT,
    events      JSONB,
    recorded_by UUID NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by  UUID,
    updated_by  UUID,
    version     INT NOT NULL DEFAULT 1,
    status      TEXT NOT NULL,
    audit_reference TEXT,
    deleted_at  TIMESTAMPTZ,
    deleted_by  UUID,
    deletion_reason TEXT
);

CREATE INDEX idx_perioperative_surgery ON perioperative_records (surgery_id);
CREATE INDEX idx_perioperative_recorded_at ON perioperative_records (recorded_at);

-- ----------------------------------------------------------------------------
-- surgery_checklists
-- ----------------------------------------------------------------------------
CREATE TABLE surgery_checklists (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    surgery_id    UUID NOT NULL REFERENCES surgeries(id),
    check_type    TEXT NOT NULL CHECK (check_type IN ('TIME_OUT','SIGN_IN','SIGN_OUT')),
    item          TEXT NOT NULL,
    completed     BOOLEAN NOT NULL DEFAULT false,
    completed_by  UUID,
    completed_at  TIMESTAMPTZ,
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

CREATE INDEX idx_surgery_checklists_surgery ON surgery_checklists (surgery_id);

-- ----------------------------------------------------------------------------
-- history tables
-- ----------------------------------------------------------------------------
SELECT ehos_make_history('surgeries');
SELECT ehos_make_history('surgery_team_members');
SELECT ehos_make_history('perioperative_records');
SELECT ehos_make_history('surgery_checklists');

-- ----------------------------------------------------------------------------
-- grants to application role
-- ----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO ehos_surgery_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_surgery_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_surgery_app;

COMMIT;