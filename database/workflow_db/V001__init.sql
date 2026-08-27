-- ============================================================================
-- EHOS  workflow_db  V001__init.sql
-- workflow-service: definitions, instances, transitions (state machine).
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- workflow_definitions — reusable workflow templates
-- ----------------------------------------------------------------------------
CREATE TABLE workflow_definitions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key             TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    version         INT NOT NULL DEFAULT 1,
    states          JSONB,
    transitions     JSONB,
    initial_state   TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID,
    updated_by      UUID,
    model_version   INT NOT NULL DEFAULT 1,
    status          TEXT NOT NULL,
    audit_reference TEXT,
    deleted_at      TIMESTAMPTZ,
    deleted_by      UUID,
    deletion_reason TEXT
);

CREATE UNIQUE INDEX uq_wf_def_key_version ON workflow_definitions (key, version) WHERE deleted_at IS NULL;
CREATE INDEX idx_wf_def_key ON workflow_definitions (key);

-- ----------------------------------------------------------------------------
-- workflow_instances — running instances of a definition
-- ----------------------------------------------------------------------------
CREATE TABLE workflow_instances (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    definition_id   UUID NOT NULL REFERENCES workflow_definitions(id),
    entity_type     TEXT NOT NULL,
    entity_id       UUID NOT NULL,
    patient_id      UUID,
    current_state   TEXT NOT NULL,
    context         JSONB,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','COMPLETED','CANCELLED','PAUSED')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID,
    updated_by      UUID,
    model_version   INT NOT NULL DEFAULT 1,
    audit_reference TEXT,
    deleted_at      TIMESTAMPTZ,
    deleted_by      UUID,
    deletion_reason TEXT
);

CREATE INDEX idx_wf_inst_entity ON workflow_instances (entity_type, entity_id);
CREATE INDEX idx_wf_inst_patient ON workflow_instances (patient_id) WHERE patient_id IS NOT NULL;
CREATE INDEX idx_wf_inst_state ON workflow_instances (current_state);

-- ----------------------------------------------------------------------------
-- workflow_transitions — state change audit trail
-- ----------------------------------------------------------------------------
CREATE TABLE workflow_transitions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id     UUID NOT NULL REFERENCES workflow_instances(id),
    from_state      TEXT NOT NULL,
    to_state        TEXT NOT NULL,
    event           TEXT NOT NULL,
    actor_id        UUID NOT NULL,
    comment         TEXT,
    metadata        JSONB,
    performed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID,
    updated_by      UUID,
    model_version   INT NOT NULL DEFAULT 1,
    status          TEXT NOT NULL,
    audit_reference TEXT,
    deleted_at      TIMESTAMPTZ,
    deleted_by      UUID,
    deletion_reason TEXT
);

CREATE INDEX idx_wf_trans_instance ON workflow_transitions (instance_id);
CREATE INDEX idx_wf_trans_from ON workflow_transitions (from_state);
CREATE INDEX idx_wf_trans_to ON workflow_transitions (to_state);

-- ----------------------------------------------------------------------------
-- history tables
-- ----------------------------------------------------------------------------
SELECT ehos_make_history('workflow_definitions');
SELECT ehos_make_history('workflow_instances');
SELECT ehos_make_history('workflow_transitions');

-- ----------------------------------------------------------------------------
-- grants
-- ----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO ehos_workflow_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_workflow_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_workflow_app;

COMMIT;
