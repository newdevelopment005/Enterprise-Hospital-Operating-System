-- ============================================================================
-- EHOS  reporting_db  V001__init.sql
-- reporting-service: report definitions, instances, scheduled reports.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- report_definitions — reusable report templates
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS report_definitions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name           VARCHAR NOT NULL,
    report_type    VARCHAR NOT NULL,
    description    TEXT,
    parameters_schema JSON,
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
    deletion_reason TEXT,
    CONSTRAINT ck_report_type CHECK (report_type IN ('PATIENT_SUMMARY','FINANCIAL','CLINICAL','OPERATIONAL','REGULATORY'))
);

-- ----------------------------------------------------------------------------
-- report_instances — execution runs of a definition
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS report_instances (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_definition_id UUID NOT NULL REFERENCES report_definitions(id),
    parameters     JSON,
    requested_by   UUID NOT NULL,
    status         VARCHAR NOT NULL DEFAULT 'QUEUED',
    result_data    JSON,
    result_url     VARCHAR,
    error_message  TEXT,
    started_at     TIMESTAMPTZ,
    completed_at   TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by     UUID,
    updated_by     UUID,
    model_version  INTEGER NOT NULL DEFAULT 1,
    audit_reference VARCHAR,
    deleted_at     TIMESTAMPTZ,
    deleted_by     UUID,
    deletion_reason TEXT,
    CONSTRAINT ck_instance_status CHECK (status IN ('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED'))
);

CREATE INDEX IF NOT EXISTS idx_instances_definition ON report_instances(report_definition_id);
CREATE INDEX IF NOT EXISTS idx_instances_requested ON report_instances(requested_by);

-- ----------------------------------------------------------------------------
-- scheduled_reports — cron-driven report scheduling
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scheduled_reports (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_definition_id UUID NOT NULL REFERENCES report_definitions(id),
    schedule_cron  VARCHAR NOT NULL,
    parameters     JSON,
    delivery_email VARCHAR,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    last_run_at    TIMESTAMPTZ,
    next_run_at    TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by     UUID,
    updated_by     UUID,
    model_version  INTEGER NOT NULL DEFAULT 1,
    audit_reference VARCHAR,
    deleted_at     TIMESTAMPTZ,
    deleted_by     UUID,
    deletion_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_sched_definition ON scheduled_reports(report_definition_id);
CREATE INDEX IF NOT EXISTS idx_sched_next_run ON scheduled_reports(next_run_at, is_active);

-- ----------------------------------------------------------------------------
-- history tables
-- ----------------------------------------------------------------------------
SELECT ehos_make_history('report_definitions');
SELECT ehos_make_history('report_instances');
SELECT ehos_make_history('scheduled_reports');

-- ----------------------------------------------------------------------------
-- grants
-- ----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO ehos_reporting_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_reporting_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_reporting_app;

COMMIT;