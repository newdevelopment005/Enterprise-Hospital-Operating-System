-- ============================================================================
-- EHOS  reporting_db / V001__init.sql
-- Service: reporting-service
-- Description: Baseline schema for the reporting database: report definitions
--   and report run executions, with per-table history triggers.
-- Design: DATABASE_DESIGN.md sections 2, 7.8, 9, 10.
-- Requires: shared 01_extensions.sql (pgcrypto, pg_trgm), 02_history_trigger.sql
--   (fn_append_history(), ehos_make_history()), 03_outbox.sql (outbox_events)
--   applied first by apply.py. No \i includes in this file.
-- Postgres 16+, lowercase snake_case, app role: ehos_reporting_app.
-- ============================================================================

BEGIN;

CREATE TABLE report_definitions (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code          TEXT NOT NULL,
    name          TEXT NOT NULL,
    category      TEXT NOT NULL,
    datasource    TEXT NOT NULL,
    params_schema JSONB,
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

CREATE UNIQUE INDEX uq_report_definitions_code ON report_definitions (code) WHERE deleted_at IS NULL;

SELECT ehos_make_history('report_definitions');

CREATE TABLE report_runs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_def_id  UUID NOT NULL REFERENCES report_definitions(id),
    parameters     JSONB,
    output_ref     TEXT,
    status         TEXT NOT NULL DEFAULT 'QUEUED' CHECK (status IN ('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED')),
    requested_by   UUID,
    started_at     TIMESTAMPTZ,
    finished_at    TIMESTAMPTZ,
    error          TEXT,
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

CREATE INDEX idx_report_runs_def_time ON report_runs (report_def_id, started_at DESC);

SELECT ehos_make_history('report_runs');

GRANT USAGE ON SCHEMA public TO ehos_reporting_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_reporting_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_reporting_app;

COMMIT;