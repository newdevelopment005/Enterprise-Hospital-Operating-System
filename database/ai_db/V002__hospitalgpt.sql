-- ============================================================================
-- EHOS  ai_db/V002__hospitalgpt.sql
-- Service:      ai-service (HospitalGPT)
-- Description:  HospitalGPT additions: conversation memory (short-term),
--               long-term memories, and live model-load registry for the
--               Model Manager / Inference Engine. Also extends the
--               ai_requests.request_type and ai_models.family CHECK lists to
--               cover chat and TTS.
-- Design:       DATABASE_DESIGN.md sections 8.1 (ai_db), 10 (cross-cutting),
--               HOSPITALGPT_ARCHITECTURE.md sections 3, 6, 7.
-- Applies after V001__init.sql (roles and shared objects already exist).
-- ============================================================================

BEGIN;

-- ============================================================================
-- Extend ai_requests.request_type with 'CHAT' (drop + recreate constraint)
-- ============================================================================
ALTER TABLE ai_requests DROP CONSTRAINT ai_requests_request_type_check;
ALTER TABLE ai_requests
    ADD CONSTRAINT ai_requests_request_type_check
    CHECK (request_type IN ('CHAT','SUMMARIZE','ANALYZE','SEARCH','DOCUMENT','TRANSCRIBE','OCR','PREDICT','AGENT'));

-- ============================================================================
-- Extend ai_models.family with 'TTS' (drop + recreate constraint)
-- ============================================================================
ALTER TABLE ai_models DROP CONSTRAINT ai_models_family_check;
ALTER TABLE ai_models
    ADD CONSTRAINT ai_models_family_check
    CHECK (family IN ('LLM','EMBEDDING','ASR','TTS','OCR','VISION','PREDICTION','AGENT'));

-- ============================================================================
-- ai_conversations — short-term conversation memory
-- ============================================================================
CREATE TABLE ai_conversations (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL,
    agent_key        TEXT,
    title            TEXT,
    model_key        TEXT,
    system_prompt_code TEXT,
    summary          TEXT,
    last_message_at  TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    version          INT NOT NULL DEFAULT 1,
    status           TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','ARCHIVED')),
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason  TEXT
);
CREATE INDEX idx_ai_conversations_user ON ai_conversations (user_id, created_at DESC) WHERE deleted_at IS NULL;
SELECT ehos_make_history('ai_conversations');

-- ============================================================================
-- ai_messages — one conversational turn (user/assistant/system/tool)
-- ============================================================================
CREATE TABLE ai_messages (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id  UUID NOT NULL REFERENCES ai_conversations(id),
    role             TEXT NOT NULL CHECK (role IN ('USER','ASSISTANT','SYSTEM','TOOL')),
    content          TEXT NOT NULL,
    tokens_in        INT,
    tokens_out       INT,
    latency_ms       INT,
    request_id       UUID REFERENCES ai_requests(id),
    sources          JSONB,
    safety_flags     JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    version          INT NOT NULL DEFAULT 1,
    status           TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE')),
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason  TEXT
);
CREATE INDEX idx_ai_messages_conversation ON ai_messages (conversation_id, created_at ASC);
SELECT ehos_make_history('ai_messages');

-- ============================================================================
-- ai_memories — long-term memory (approved hospital knowledge / config only)
-- ============================================================================
CREATE TABLE ai_memories (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL,
    memory_type      TEXT NOT NULL CHECK (memory_type IN ('EPISODIC','FACT','WORKFLOW','PREFERENCE','KNOWLEDGE')),
    content          TEXT NOT NULL,
    importance       INT NOT NULL DEFAULT 1 CHECK (importance BETWEEN 1 AND 5),
    embedding_id     TEXT,
    source_request_id UUID REFERENCES ai_requests(id),
    refresh_at       TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    version          INT NOT NULL DEFAULT 1,
    status           TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE')),
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason  TEXT
);
CREATE INDEX idx_ai_memories_user ON ai_memories (user_id, memory_type) WHERE deleted_at IS NULL;
SELECT ehos_make_history('ai_memories');

-- ============================================================================
-- ai_model_loads — live load state for the Model Manager / Inference Engine
-- ============================================================================
CREATE TABLE ai_model_loads (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id      UUID NOT NULL REFERENCES ai_models(id),
    runtime       TEXT NOT NULL DEFAULT 'OLLAMA' CHECK (runtime IN ('OLLAMA','LLAMACPP','MOCK')),
    load_status   TEXT NOT NULL DEFAULT 'UNLOADED'
                  CHECK (load_status IN ('LOADING','LOADED','UNLOADING','UNLOADED','ERROR','RETIRED')),
    base_url      TEXT,
    slot_id       TEXT,
    gpu_layers    INT,
    memory_mb     INT,
    load_error    TEXT,
    loaded_at     TIMESTAMPTZ,
    last_used_at  TIMESTAMPTZ,
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
CREATE INDEX idx_ai_model_loads_model ON ai_model_loads (model_id) WHERE deleted_at IS NULL;
SELECT ehos_make_history('ai_model_loads');

-- ============================================================================
-- Grants (new tables must be granted; ALL TABLES in V001 only covered then-existing tables)
-- ============================================================================
GRANT USAGE ON SCHEMA public TO ehos_ai_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_ai_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_ai_app;

COMMIT;