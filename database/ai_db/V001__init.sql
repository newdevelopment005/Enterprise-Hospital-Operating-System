-- ============================================================================
-- EHOS  ai_db/V001__init.sql
-- Service:      ai-gateway + ai-family
-- Description:  AI tier schema: model registry, immutable AI request log,
--               human-in-the-loop approvals, prompt templates, agent
--               definitions/runs/actions, predictions, model evaluations,
--               and clinician feedback on AI output.
-- Design:       DATABASE_DESIGN.md sections 8.1 (ai_db), 9 (event outbox),
--               10 (cross-cutting standards), 2 (global conventions).
-- NOTE:         AI services consume domain events and read other services'
--               data ONLY via permission-scoped data APIs; they never access
--               another service's database directly.
-- Shared objects (pgcrypto, pg_trgm, fn_append_history(), ehos_make_history(),
-- outbox_events) are applied FIRST by apply.py before this migration runs.
-- ============================================================================

BEGIN;

-- ============================================================================
-- ai_models — model registry
-- ============================================================================
CREATE TABLE ai_models (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_key        TEXT NOT NULL,
    family           TEXT NOT NULL CHECK (family IN ('LLM','EMBEDDING','ASR','OCR','VISION','PREDICTION','AGENT')),
    base_name        TEXT NOT NULL,
    version          TEXT NOT NULL,
    quantization     TEXT,
    context_window   INT,
    purpose          TEXT,
    training_source  TEXT,
    artifact_ref     TEXT,
    approval_status  TEXT NOT NULL DEFAULT 'PENDING'
                     CHECK (approval_status IN ('PENDING','REVIEW','APPROVED','REJECTED','DEPRECATED','RETIRED')),
    approved_by      UUID,
    approved_at      TIMESTAMPTZ,
    attributes       JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    status           TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE')),
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason  TEXT,
    UNIQUE (model_key)
);
CREATE INDEX idx_ai_models_status ON ai_models (approval_status, family) WHERE deleted_at IS NULL;
SELECT ehos_make_history('ai_models');

-- ============================================================================
-- ai_requests — immutable append-only request log (created_at + audit_reference
-- only; no updated_at, no soft delete). It is itself a log, so
-- ehos_make_history is intentionally skipped.
-- ============================================================================
CREATE TABLE ai_requests (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id       TEXT NOT NULL,
    user_id          UUID NOT NULL,
    model_id         UUID REFERENCES ai_models(id),
    request_type     TEXT NOT NULL
                     CHECK (request_type IN ('SUMMARIZE','ANALYZE','SEARCH','DOCUMENT','TRANSCRIBE','OCR','PREDICT','AGENT')),
    context_type     TEXT,
    context_ref      UUID,
    input_ref        TEXT,
    input_hash       TEXT,
    response_ref     TEXT,
    response_hash    TEXT,
    safety_flags     JSONB,
    approval_level   INT,
    approval_status  TEXT NOT NULL DEFAULT 'NO_APPROVAL_REQUIRED'
                     CHECK (approval_status IN ('NO_APPROVAL_REQUIRED','PENDING','APPROVED','REJECTED','OVERRIDDEN')),
    latency_ms       INT,
    tokens_in        INT,
    tokens_out       INT,
    error            TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at     TIMESTAMPTZ,
    audit_reference  TEXT,
    UNIQUE (request_id)
);
CREATE INDEX idx_ai_requests_user ON ai_requests (user_id, created_at DESC);
CREATE INDEX idx_ai_requests_model_time ON ai_requests (model_id, created_at DESC);
CREATE INDEX idx_ai_requests_context ON ai_requests (context_type, context_ref) WHERE context_ref IS NOT NULL;

-- ============================================================================
-- ai_request_approvals — human-in-the-loop decisions
-- ============================================================================
CREATE TABLE ai_request_approvals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ai_request_id   UUID NOT NULL REFERENCES ai_requests(id),
    level           INT NOT NULL CHECK (level BETWEEN 1 AND 4),
    required_role   TEXT NOT NULL,
    approver_id     UUID,
    status          TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING','APPROVED','REJECTED','REASSIGNED')),
    decided_at      TIMESTAMPTZ,
    comments        TEXT,
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
CREATE INDEX idx_ai_approvals_request ON ai_request_approvals (ai_request_id);
SELECT ehos_make_history('ai_request_approvals');

-- ============================================================================
-- prompt_templates
-- ============================================================================
CREATE TABLE prompt_templates (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code          TEXT NOT NULL,
    name          TEXT NOT NULL,
    purpose       TEXT,
    template      TEXT NOT NULL,
    vars_schema   JSONB,
    safety_rules  JSONB,
    version       INT NOT NULL DEFAULT 1,
    is_active     BOOLEAN NOT NULL DEFAULT true,
    approved_by   UUID,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by    UUID,
    updated_by    UUID,
    status        TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE')),
    audit_reference TEXT,
    deleted_at    TIMESTAMPTZ,
    deleted_by    UUID,
    deletion_reason TEXT,
    UNIQUE (code)
);
SELECT ehos_make_history('prompt_templates');

-- ============================================================================
-- agent_definitions
-- ============================================================================
CREATE TABLE agent_definitions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key             TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    capabilities    JSONB,
    allowed_tools   JSONB,
    config          JSONB,
    approval_policy JSONB,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    version         INT NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID,
    updated_by      UUID,
    status          TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE')),
    audit_reference TEXT,
    deleted_at      TIMESTAMPTZ,
    deleted_by      UUID,
    deletion_reason TEXT,
    UNIQUE (key)
);
SELECT ehos_make_history('agent_definitions');

-- ============================================================================
-- agent_runs
-- ============================================================================
CREATE TABLE agent_runs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id     UUID NOT NULL REFERENCES agent_definitions(id),
    run_token    TEXT NOT NULL,
    user_id      UUID NOT NULL,
    goal         TEXT,
    status       TEXT NOT NULL DEFAULT 'RUNNING'
                 CHECK (status IN ('RUNNING','AWAITING_APPROVAL','COMPLETED','FAILED','CANCELLED','BLOCKED')),
    result_ref   TEXT,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by   UUID,
    updated_by   UUID,
    version      INT NOT NULL DEFAULT 1,
    audit_reference TEXT,
    deleted_at   TIMESTAMPTZ,
    deleted_by   UUID,
    deletion_reason TEXT,
    UNIQUE (run_token)
);
CREATE INDEX idx_agent_runs_agent ON agent_runs (agent_id, started_at DESC);
SELECT ehos_make_history('agent_runs');

-- ============================================================================
-- agent_actions
-- ============================================================================
CREATE TABLE agent_actions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id            UUID NOT NULL REFERENCES agent_runs(id),
    action_type       TEXT NOT NULL,
    tool              TEXT,
    input             JSONB,
    output            JSONB,
    requires_approval BOOLEAN NOT NULL DEFAULT false,
    approval_status   TEXT NOT NULL DEFAULT 'NO_APPROVAL_REQUIRED'
                      CHECK (approval_status IN ('NO_APPROVAL_REQUIRED','PENDING','APPROVED','REJECTED')),
    performed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by        UUID,
    updated_by        UUID,
    version           INT NOT NULL DEFAULT 1,
    status            TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE')),
    audit_reference   TEXT,
    deleted_at        TIMESTAMPTZ,
    deleted_by        UUID,
    deletion_reason   TEXT
);
CREATE INDEX idx_agent_actions_run ON agent_actions (run_id);
SELECT ehos_make_history('agent_actions');

-- ============================================================================
-- predictions — prediction-service outputs
-- ============================================================================
CREATE TABLE predictions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prediction_key TEXT NOT NULL,
    entity_type    TEXT,
    entity_id      UUID,
    horizon        TEXT,
    window_from    DATE,
    window_to      DATE,
    model_id       UUID REFERENCES ai_models(id),
    forecast       JSONB NOT NULL,
    confidence     NUMERIC(5,4),
    status         TEXT NOT NULL DEFAULT 'VALID' CHECK (status IN ('VALID','SUPERSEDED','CANCELLED')),
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
CREATE INDEX idx_predictions_key_window ON predictions (prediction_key, window_from) WHERE deleted_at IS NULL;
CREATE INDEX idx_predictions_model ON predictions (model_id);
SELECT ehos_make_history('predictions');

-- ============================================================================
-- model_evaluations — evaluation-service outputs
-- ============================================================================
CREATE TABLE model_evaluations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id      UUID NOT NULL REFERENCES ai_models(id),
    dataset_ref   TEXT,
    metrics       JSONB NOT NULL,
    evaluated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    evaluated_by  UUID,
    verdict       TEXT CHECK (verdict IN ('PASS','WARN','FAIL')),
    notes         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by    UUID,
    updated_by    UUID,
    version       INT NOT NULL DEFAULT 1,
    status        TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE')),
    audit_reference TEXT,
    deleted_at    TIMESTAMPTZ,
    deleted_by    UUID,
    deletion_reason TEXT
);
CREATE INDEX idx_model_evaluations_model ON model_evaluations (model_id, evaluated_at DESC);
SELECT ehos_make_history('model_evaluations');

-- ============================================================================
-- ai_feedback — clinician feedback on AI output
-- ============================================================================
CREATE TABLE ai_feedback (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ai_request_id UUID NOT NULL REFERENCES ai_requests(id),
    user_id       UUID NOT NULL,
    rating        SMALLINT CHECK (rating BETWEEN 1 AND 5),
    category      TEXT,
    comment       TEXT,
    accepted      BOOLEAN,
    feedback_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by    UUID,
    updated_by    UUID,
    version       INT NOT NULL DEFAULT 1,
    status        TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE')),
    audit_reference TEXT,
    deleted_at    TIMESTAMPTZ,
    deleted_by    UUID,
    deletion_reason TEXT
);
CREATE INDEX idx_ai_feedback_request ON ai_feedback (ai_request_id);
SELECT ehos_make_history('ai_feedback');

-- ============================================================================
-- Grants
-- ============================================================================
GRANT USAGE ON SCHEMA public TO ehos_ai_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_ai_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_ai_app;

COMMIT;