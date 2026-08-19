-- ============================================================================
-- EHOS  payroll_db / V001__init.sql
-- Service: payroll-service
-- Description: Baseline schema for the payroll database: payroll periods,
--   payroll runs, payroll inputs (per-employee computation basis) and payslips,
--   with per-table history triggers.
-- Design: DATABASE_DESIGN.md sections 2, 7.7, 9, 10.
-- Requires: shared 01_extensions.sql (pgcrypto, pg_trgm), 02_history_trigger.sql
--   (fn_append_history(), ehos_make_history()), 03_outbox.sql (outbox_events)
--   applied first by apply.py. No \i includes in this file.
-- Postgres 16+, lowercase snake_case, app role: ehos_payroll_app.
-- ============================================================================

BEGIN;

CREATE TABLE payroll_periods (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    period_key    TEXT NOT NULL,
    starts_on     DATE NOT NULL,
    ends_on       DATE NOT NULL,
    pay_run_date  DATE,
    status        TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','PROCESSING','APPROVED','PAID','CLOSED')),
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

CREATE UNIQUE INDEX uq_payroll_periods_period_key ON payroll_periods (period_key) WHERE deleted_at IS NULL;

SELECT ehos_make_history('payroll_periods');

CREATE TABLE payroll_runs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    period_id    UUID NOT NULL REFERENCES payroll_periods(id),
    run_type     TEXT NOT NULL DEFAULT 'MONTHLY' CHECK (run_type IN ('MONTHLY','BONUS','OVERTIME','OFF_CYCLE')),
    run_no       TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','PROCESSING','VALIDATED','APPROVED','PAID','FAILED')),
    mode         TEXT CHECK (mode IN ('AUTO','MANUAL')),
    run_by       UUID,
    started_at   TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by   UUID,
    updated_by   UUID,
    version      INT NOT NULL DEFAULT 1,
    audit_reference TEXT,
    deleted_at   TIMESTAMPTZ,
    deleted_by   UUID,
    deletion_reason TEXT
);

CREATE UNIQUE INDEX uq_payroll_runs_run_no ON payroll_runs (run_no) WHERE deleted_at IS NULL;
CREATE INDEX idx_payroll_runs_period ON payroll_runs (period_id);

SELECT ehos_make_history('payroll_runs');

CREATE TABLE payroll_inputs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id         UUID REFERENCES payroll_runs(id),
    employee_id    UUID NOT NULL,
    basic_pay      NUMERIC(12,2),
    allowances     NUMERIC(12,2) NOT NULL DEFAULT 0,
    overtime_hours NUMERIC(6,2) NOT NULL DEFAULT 0,
    overtime_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    deductions     NUMERIC(12,2) NOT NULL DEFAULT 0,
    tax            NUMERIC(12,2) NOT NULL DEFAULT 0,
    social_insurance NUMERIC(12,2) NOT NULL DEFAULT 0,
    net_pay        NUMERIC(12,2) NOT NULL DEFAULT 0,
    pay_currency   TEXT NOT NULL DEFAULT 'EGP',
    period_start   DATE,
    period_end     DATE,
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

CREATE INDEX idx_payroll_inputs_run ON payroll_inputs (run_id);
CREATE INDEX idx_payroll_inputs_employee ON payroll_inputs (employee_id);

SELECT ehos_make_history('payroll_inputs');

CREATE TABLE payslips (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id         UUID NOT NULL REFERENCES payroll_runs(id),
    input_id       UUID REFERENCES payroll_inputs(id),
    employee_id    UUID NOT NULL,
    payslip_no     TEXT NOT NULL,
    earnings_json  JSONB,
    deductions_json JSONB,
    net_amount     NUMERIC(12,2) NOT NULL,
    issued_at      TIMESTAMPTZ,
    status         TEXT NOT NULL DEFAULT 'GENERATED' CHECK (status IN ('GENERATED','VIEWED','EMAILED','ACKNOWLEDGED')),
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

CREATE UNIQUE INDEX uq_payslips_payslip_no ON payslips (payslip_no) WHERE deleted_at IS NULL;
CREATE INDEX idx_payslips_run ON payslips (run_id);
CREATE INDEX idx_payslips_input ON payslips (input_id);

SELECT ehos_make_history('payslips');

GRANT USAGE ON SCHEMA public TO ehos_payroll_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_payroll_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_payroll_app;

COMMIT;