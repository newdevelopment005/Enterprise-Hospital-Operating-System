-- ============================================================================
-- EHOS  configuration_db/V001__init.sql
-- configuration-service platform database: feature flags and per-service
-- configuration entries.
-- Implements DATABASE_DESIGN.md section 4.3 using global conventions 2.5
-- (common row block), 2.6 (soft delete), 2.7 (history), 2.8 (indexes) and 9
-- (event outbox). Shared files are applied first by apply.py (01_extensions,
-- 02_history_trigger, 03_outbox); fn_append_history(), ehos_make_history()
-- and outbox_events are assumed to already exist and are not recreated here.
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- feature_flags
-- ---------------------------------------------------------------------------
CREATE TABLE feature_flags (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    namespace       TEXT NOT NULL DEFAULT 'default',
    enabled         BOOLEAN NOT NULL DEFAULT false,
    rules           JSONB,
    start_at        TIMESTAMPTZ,
    end_at          TIMESTAMPTZ,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID,
    updated_by      UUID,
    version         INT NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'ACTIVE'
                    CHECK (status IN ('ACTIVE','INACTIVE')),
    audit_reference TEXT,
    deleted_at      TIMESTAMPTZ,
    deleted_by      UUID,
    deletion_reason TEXT
);

CREATE UNIQUE INDEX uq_feature_flags_namespace_name
    ON feature_flags (namespace, name) WHERE deleted_at IS NULL;

SELECT ehos_make_history('feature_flags');

-- ---------------------------------------------------------------------------
-- configuration_entries
-- ---------------------------------------------------------------------------
CREATE TABLE configuration_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service         TEXT NOT NULL,
    key             TEXT NOT NULL,
    value_json      JSONB NOT NULL,
    value_type      TEXT NOT NULL CHECK (value_type IN ('STRING','INT','BOOL','JSON','SECRET')),
    environment     TEXT NOT NULL DEFAULT 'production'
                    CHECK (environment IN ('development','test','staging','production')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID,
    updated_by      UUID,
    version         INT NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'ACTIVE'
                    CHECK (status IN ('ACTIVE','INACTIVE')),
    audit_reference TEXT,
    deleted_at      TIMESTAMPTZ,
    deleted_by      UUID,
    deletion_reason TEXT
);

CREATE UNIQUE INDEX uq_configuration_entries_service_key_environment
    ON configuration_entries (service, key, environment) WHERE deleted_at IS NULL;
CREATE INDEX idx_configuration_service ON configuration_entries (service, environment);

SELECT ehos_make_history('configuration_entries');

COMMIT;

-- ---------------------------------------------------------------------------
-- application role grants
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO ehos_configuration_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_configuration_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_configuration_app;