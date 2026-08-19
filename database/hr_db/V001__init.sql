-- ============================================================================
-- EHOS  hr_db / V001__init.sql
-- Service: hr-service
-- Description: Baseline schema for the HR database: departments, employees,
--   employee credentials (licenses/certifications), staff shifts, shift
--   assignments and attendance clock records, with per-table history triggers.
-- Design: DATABASE_DESIGN.md sections 2, 7.6, 9, 10.
-- Requires: shared 01_extensions.sql (pgcrypto, pg_trgm), 02_history_trigger.sql
--   (fn_append_history(), ehos_make_history()), 03_outbox.sql (outbox_events)
--   applied first by apply.py. No \i includes in this file.
-- Postgres 16+, lowercase snake_case, app role: ehos_hr_app.
-- ============================================================================

BEGIN;

CREATE TABLE departments (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code           TEXT NOT NULL,
    name           TEXT NOT NULL,
    cost_center_id UUID,
    parent_id      UUID REFERENCES departments(id),
    head_employee_id UUID,
    is_active      BOOLEAN NOT NULL DEFAULT true,
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

CREATE UNIQUE INDEX uq_departments_code ON departments (code) WHERE deleted_at IS NULL;
CREATE INDEX idx_departments_parent ON departments (parent_id);

SELECT ehos_make_history('departments');

CREATE TABLE employees (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID,
    employee_number  TEXT NOT NULL,
    first_name       TEXT NOT NULL,
    last_name        TEXT NOT NULL,
    date_of_birth    DATE,
    gender           TEXT,
    national_identifier TEXT,
    hire_date        DATE,
    termination_date DATE,
    department_id    UUID REFERENCES departments(id),
    position_title   TEXT,
    employment_type  TEXT CHECK (employment_type IN ('FULL_TIME','PART_TIME','CONTRACT','PER_DIEM','VOLUNTEER')),
    primary_specialty TEXT,
    status           TEXT NOT NULL DEFAULT 'ACTIVE'
                     CHECK (status IN ('ACTIVE','ON_LEAVE','TERMINATED','INACTIVE')),
    contact          JSONB,
    emergency_contact JSONB,
    attributes       JSONB,
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

CREATE UNIQUE INDEX uq_employees_employee_number ON employees (employee_number) WHERE deleted_at IS NULL;
CREATE INDEX idx_employees_name_trgm ON employees USING gin (first_name gin_trgm_ops, last_name gin_trgm_ops);
CREATE INDEX idx_employees_department ON employees (department_id) WHERE deleted_at IS NULL AND status = 'ACTIVE';

SELECT ehos_make_history('employees');

CREATE TABLE employee_credentials (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id      UUID NOT NULL REFERENCES employees(id),
    credential_type  TEXT NOT NULL,
    credential_number TEXT,
    issuing_body     TEXT,
    issued_date      DATE,
    expiry_date      DATE NOT NULL,
    attachment_ref   TEXT,
    status           TEXT NOT NULL DEFAULT 'VALID' CHECK (status IN ('VALID','EXPIRING','EXPIRED','SUSPENDED','REVOKED')),
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

CREATE INDEX idx_credentials_expiry ON employee_credentials (expiry_date, status) WHERE deleted_at IS NULL;
CREATE INDEX idx_employee_credentials_employee ON employee_credentials (employee_id);

SELECT ehos_make_history('employee_credentials');

CREATE TABLE staff_shifts (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    department_id UUID,
    shift_type    TEXT NOT NULL CHECK (shift_type IN ('MORNING','EVENING','NIGHT','ON_CALL','SPECIAL')),
    start_time    TIME NOT NULL,
    end_time      TIME NOT NULL,
    day_mask      SMALLINT[],
    is_active     BOOLEAN NOT NULL DEFAULT true,
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

SELECT ehos_make_history('staff_shifts');

CREATE TABLE shift_assignments (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id   UUID NOT NULL REFERENCES employees(id),
    shift_id      UUID NOT NULL REFERENCES staff_shifts(id),
    work_date     DATE NOT NULL,
    status        TEXT NOT NULL DEFAULT 'ASSIGNED' CHECK (status IN ('ASSIGNED','CONFIRMED','DROPPED','COVERED')),
    duration_min  INT,
    notes         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by    UUID,
    updated_by    UUID,
    version       INT NOT NULL DEFAULT 1,
    audit_reference TEXT,
    deleted_at    TIMESTAMPTZ,
    deleted_by    UUID,
    deletion_reason TEXT
);

CREATE UNIQUE INDEX uq_shift_assignments_employee_work_date
    ON shift_assignments (employee_id, work_date)
    WHERE deleted_at IS NULL;
CREATE INDEX idx_shift_assignments_date ON shift_assignments (work_date, shift_id);

SELECT ehos_make_history('shift_assignments');

CREATE TABLE attendance (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id   UUID NOT NULL REFERENCES employees(id),
    clock_in      TIMESTAMPTZ NOT NULL,
    clock_out     TIMESTAMPTZ,
    hours_worked  NUMERIC(6,2),
    source        TEXT CHECK (source IN ('FINGERPRINT','BADGE','MOBILE','MANUAL')),
    verified_by   UUID,
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

CREATE INDEX idx_attendance_employee ON attendance (employee_id, clock_in DESC);

SELECT ehos_make_history('attendance');

GRANT USAGE ON SCHEMA public TO ehos_hr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_hr_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_hr_app;

COMMIT;