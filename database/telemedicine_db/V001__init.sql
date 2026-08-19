-- ============================================================================
-- EHOS  telemedicine_db  V001__init.sql
-- telemedicine-service: telehealth sessions & remote monitoring readings.
-- Design: DATABASE_DESIGN.md sections 6.10, 2.5-2.7, 10; role 00_db_roles.sql.
-- Shared objects (pgcrypto, pg_trgm, fn_append_history(), ehos_make_history(),
-- outbox_events) are applied FIRST by apply.py; not included here.
-- Postgres 16+, lowercase snake_case.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- telehealth_sessions
-- ----------------------------------------------------------------------------
CREATE TABLE telehealth_sessions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id        UUID NOT NULL,
    provider_id       UUID NOT NULL,
    appointment_id    UUID,
    mode              TEXT NOT NULL CHECK (mode IN ('VIDEO','AUDIO','CHAT','REMOTE_MONITORING')),
    scheduled_start   TIMESTAMPTZ NOT NULL,
    actual_start      TIMESTAMPTZ,
    actual_end        TIMESTAMPTZ,
    session_token_ref TEXT,
    recording_ref     TEXT,
    status            TEXT NOT NULL DEFAULT 'SCHEDULED' CHECK (status IN ('SCHEDULED','IN_PROGRESS','COMPLETED','CANCELLED','NO_SHOW','FAILED')),
    outcome           TEXT,
    notes_shared      BOOLEAN NOT NULL DEFAULT false,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by        UUID,
    updated_by        UUID,
    version           INT NOT NULL DEFAULT 1,
    audit_reference   TEXT,
    deleted_at        TIMESTAMPTZ,
    deleted_by        UUID,
    deletion_reason   TEXT
);

CREATE INDEX idx_telehealth_patient ON telehealth_sessions (patient_id, scheduled_start);
CREATE INDEX idx_telehealth_provider ON telehealth_sessions (provider_id);

-- ----------------------------------------------------------------------------
-- remote_monitoring_readings — high-volume vitals stream (partitioned)
-- ----------------------------------------------------------------------------
CREATE TABLE remote_monitoring_readings (
    id            UUID NOT NULL DEFAULT gen_random_uuid(),
    patient_id    UUID NOT NULL,
    device_id     TEXT NOT NULL,
    reading_type  TEXT NOT NULL CHECK (reading_type IN ('BP','HR','GLUCOSE','SPO2','TEMP','WEIGHT','ECG')),
    value         JSONB NOT NULL,
    unit          TEXT,
    captured_at   TIMESTAMPTZ NOT NULL,
    -- PG16 requires PK on partitioned tables to include the partition key:
    PRIMARY KEY (id, captured_at),
    source        TEXT,
    alert_level   TEXT CHECK (alert_level IN ('NORMAL','WARNING','CRITICAL')),
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
)
PARTITION BY RANGE (captured_at);

CREATE TABLE remote_monitoring_readings_default PARTITION OF remote_monitoring_readings FOR VALUES FROM (MINVALUE) TO (MAXVALUE);

CREATE INDEX idx_rmr_patient_time ON remote_monitoring_readings (patient_id, captured_at DESC);
CREATE INDEX idx_rmr_device ON remote_monitoring_readings (device_id);

-- No ehos_make_history('remote_monitoring_readings'): the table is
-- RANGE-partitioned on captured_at (design §2.9 / §6.10); history trigger
-- tables cannot be partitioned here and the readings stream is append-only.

-- ----------------------------------------------------------------------------
-- history tables
-- ----------------------------------------------------------------------------
SELECT ehos_make_history('telehealth_sessions');

-- ----------------------------------------------------------------------------
-- grants to application role
-- ----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO ehos_telemedicine_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_telemedicine_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_telemedicine_app;

COMMIT;