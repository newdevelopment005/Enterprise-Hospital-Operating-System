-- ============================================================================
-- EHOS  workflow_db  V001__init.sql
-- workflow-service: workflow definitions, instances & transition audit trail.
-- Design: DATABASE_DESIGN.md sections 6.11, 2.5-2.7, 10; role 00_db_roles.sql.
-- Shared objects (pgcrypto, pg_trgm, fn_append_history(), ehos_make_history(),
-- outbox_events) are applied FIRST by apply.py; not included here.
-- Postgres 16+, lowercase snake_case.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- workflow_definitions
-- ----------------------------------------------------------------------------
CREATE TABLE workflow_definitions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key             TEXT NOT NULL,
    name            TEXT NOT NULL,
    domain          TEXT NOT NULL,
    version         INT NOT NULL,
    definition_json JSONB NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    status          TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID,
    updated_by      UUID,
    audit_reference TEXT,
    deleted_at      TIMESTAMPTZ,
    deleted_by      UUID,
    deletion_reason TEXT
);

CREATE UNIQUE INDEX uq_workflow_definitions_key_version ON workflow_definitions (key, version) WHERE deleted_at IS NULL;
CREATE INDEX idx_workflow_definitions_domain ON workflow_definitions (domain);

-- ----------------------------------------------------------------------------
-- workflow_instances
-- ----------------------------------------------------------------------------
CREATE TABLE workflow_instances (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    definition_id UUID NOT NULL REFERENCES workflow_definitions(id),
    workflow_key  TEXT NOT NULL,
    version       INT NOT NULL,
    entity_type   TEXT,
    entity_id     UUID,
    current_state TEXT NOT NULL,
    context       JSONB,
    started_by    UUID,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at      TIMESTAMPTZ,
    status        TEXT NOT NULL DEFAULT 'RUNNING' CHECK (status IN ('RUNNING','COMPLETED','TERMINATED','SUSPENDED')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by    UUID,
    updated_by    UUID,
    audit_reference TEXT,
    deleted_at    TIMESTAMPTZ,
    deleted_by    UUID,
    deletion_reason TEXT
);

CREATE INDEX idx_workflow_entity ON workflow_instances (entity_type, entity_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_workflow_state ON workflow_instances (current_state, status);
CREATE INDEX idx_workflow_definition ON workflow_instances (definition_id);

-- ----------------------------------------------------------------------------
-- workflow_transitions
-- ----------------------------------------------------------------------------
CREATE TABLE workflow_transitions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id    UUID NOT NULL REFERENCES workflow_instances(id),
    from_state     TEXT,
    to_state       TEXT NOT NULL,
    event          TEXT,
    action_ref     TEXT,
    performed_by   UUID,
    performed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    guard_result   JSONB,
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

CREATE INDEX idx_workflow_transitions_instance ON workflow_transitions (instance_id, performed_at);

-- ----------------------------------------------------------------------------
-- history tables
-- ----------------------------------------------------------------------------
SELECT ehos_make_history('workflow_definitions');
SELECT ehos_make_history('workflow_instances');
SELECT ehos_make_history('workflow_transitions');

-- ----------------------------------------------------------------------------
-- grants to application role
-- ----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO ehos_workflow_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_workflow_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_workflow_app;

COMMIT;