-- ============================================================================
-- EHOS  audit_db/V001__init.sql
-- audit-service platform database: immutable, hash-chained audit trail, the
-- distributed event store, saga tracking, integrity verification and archives.
-- Implements DATABASE_DESIGN.md section 4.1 using global conventions 2.5
-- (common row block), 2.6 (soft delete), 2.7 (history), 2.8 (indexes) and 9
-- (event outbox). Shared files are applied first by apply.py (01_extensions,
-- 02_history_trigger, 03_outbox); fn_append_history(), ehos_make_history()
-- and outbox_events are assumed to already exist and are not recreated here.
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- audit_logs : immutable per-action records, hash-chained (append-only)
-- ---------------------------------------------------------------------------
CREATE TABLE audit_logs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id         UUID NOT NULL,
    correlation_id   TEXT,
    user_id          UUID,
    service          TEXT NOT NULL,
    action           TEXT NOT NULL,
    resource_type    TEXT NOT NULL,
    resource_id      UUID,
    old_value        JSONB,
    new_value        JSONB,
    ip_address       INET,
    user_agent       TEXT,
    occurred_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    prev_hash        TEXT,
    payload_hash     TEXT NOT NULL,
    chain_hash       TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    version          INT NOT NULL DEFAULT 1,
    status           TEXT NOT NULL DEFAULT 'RECORDED'
                     CHECK (status IN ('RECORDED','ARCHIVED')),
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason  TEXT
);

CREATE INDEX idx_audit_logs_service_time ON audit_logs (service, occurred_at);
CREATE INDEX idx_audit_logs_user ON audit_logs (user_id);
CREATE INDEX idx_audit_logs_resource ON audit_logs (resource_type, resource_id);
CREATE INDEX idx_audit_logs_correlation ON audit_logs (correlation_id);
CREATE UNIQUE INDEX uq_audit_logs_event_id ON audit_logs (event_id) WHERE event_id IS NOT NULL;

-- append-only: history trigger still keeps an immutable copy of every mutation
SELECT ehos_make_history('audit_logs');

-- ---------------------------------------------------------------------------
-- events : partitioned event store, monthly by occurred_at
-- ---------------------------------------------------------------------------
CREATE TABLE events (
    id             UUID NOT NULL DEFAULT gen_random_uuid(),
    event_id       UUID NOT NULL,
    event_type     TEXT NOT NULL,
    event_version  INT  NOT NULL DEFAULT 1,
    source         TEXT NOT NULL,
    correlation_id TEXT,
    user_id        UUID,
    payload        JSONB NOT NULL,
    occurred_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    status         TEXT NOT NULL DEFAULT 'RECEIVED'
                   CHECK (status IN ('RECEIVED','PROCESSED','FAILED','SKIPPED')),
    processed_at   TIMESTAMPTZ,
    -- PG16 requires unique/primary keys on partitioned tables to include the
    -- partition key columns, so occurred_at is added to both constraints.
    PRIMARY KEY (id, occurred_at),
    UNIQUE (event_id, occurred_at)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE events_default PARTITION OF events FOR VALUES FROM (MINVALUE) TO (MAXVALUE);

CREATE INDEX idx_events_type_time ON events (event_type, occurred_at);
CREATE INDEX idx_events_correlation ON events (correlation_id);
-- no ehos_make_history for events: append-only partition store

-- ---------------------------------------------------------------------------
-- event_sagas : saga tracking across services
-- ---------------------------------------------------------------------------
CREATE TABLE event_sagas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    saga_id         TEXT NOT NULL,
    aggregate       TEXT,
    operation       TEXT,
    steps           JSONB,
    status          TEXT NOT NULL DEFAULT 'RUNNING'
                    CHECK (status IN ('RUNNING','COMPLETED','COMPENSATED','FAILED')),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
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

-- saga_id is the external correlation key used to locate a saga
CREATE INDEX idx_event_sagas_saga_id ON event_sagas (saga_id);

SELECT ehos_make_history('event_sagas');

-- ---------------------------------------------------------------------------
-- integrity_verifications : scheduled hash-chain verification results
-- ---------------------------------------------------------------------------
CREATE TABLE integrity_verifications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    checked_from    TIMESTAMPTZ,
    checked_to      TIMESTAMPTZ,
    verified        BOOLEAN NOT NULL,
    anomalies_found INT,
    details         JSONB,
    performed_by    UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID,
    updated_by      UUID,
    version         INT NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'RUNNING'
                    CHECK (status IN ('RUNNING','COMPLETED','FAILED')),
    audit_reference TEXT,
    deleted_at      TIMESTAMPTZ,
    deleted_by      UUID,
    deletion_reason TEXT
);

SELECT ehos_make_history('integrity_verifications');

-- ---------------------------------------------------------------------------
-- audit_archives : frozen partition archives catalogued for object storage
-- ---------------------------------------------------------------------------
CREATE TABLE audit_archives (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    archive_id      TEXT NOT NULL,
    period_start    DATE,
    period_end      DATE,
    storage_ref     TEXT,
    row_count       BIGINT,
    archived_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID,
    updated_by      UUID,
    version         INT NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'AVAILABLE'
                    CHECK (status IN ('AVAILABLE','RESTORED','PURGED')),
    audit_reference TEXT,
    deleted_at      TIMESTAMPTZ,
    deleted_by      UUID,
    deletion_reason TEXT
);

CREATE UNIQUE INDEX uq_audit_archives_archive_id ON audit_archives (archive_id) WHERE deleted_at IS NULL;

SELECT ehos_make_history('audit_archives');

COMMIT;

-- ---------------------------------------------------------------------------
-- application role grants
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO ehos_audit_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_audit_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_audit_app;