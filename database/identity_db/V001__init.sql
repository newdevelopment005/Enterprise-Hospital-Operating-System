-- ============================================================================
-- EHOS  identity_db/V001__init.sql
-- identity-service platform database: read-side mirror of Keycloak users plus
-- user MFA and session state (Keycloak remains the identity source of truth).
-- Implements DATABASE_DESIGN.md section 4.4 using global conventions 2.5
-- (common row block), 2.6 (soft delete), 2.7 (history), 2.8 (indexes) and 9
-- (event outbox). Shared files are applied first by apply.py (01_extensions,
-- 02_history_trigger, 03_outbox); fn_append_history(), ehos_make_history()
-- and outbox_events are assumed to already exist and are not recreated here.
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- users : Keycloak mirror (id maps to the Keycloak subject)
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- maps to Keycloak sub
    username         TEXT NOT NULL,
    email            TEXT NOT NULL,
    email_verified   BOOLEAN NOT NULL DEFAULT false,
    full_name        TEXT,
    given_name       TEXT,
    family_name      TEXT,
    preferred_locale TEXT DEFAULT 'en',
    enabled          BOOLEAN NOT NULL DEFAULT true,
    last_login_at    TIMESTAMPTZ,
    attributes       JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    version          INT NOT NULL DEFAULT 1,
    status           TEXT NOT NULL DEFAULT 'ACTIVE'
                     CHECK (status IN ('ACTIVE','LOCKED','DISABLED')),
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason  TEXT
);

CREATE UNIQUE INDEX uq_users_username ON users (username) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX uq_users_email ON users (email) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_email_trgm ON users USING gin (email gin_trgm_ops);

SELECT ehos_make_history('users');

-- ---------------------------------------------------------------------------
-- user_mfa
-- ---------------------------------------------------------------------------
CREATE TABLE user_mfa (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    method          TEXT NOT NULL CHECK (method IN ('TOTP','SMS','EMAIL','WEBAUTHN')),
    secret_ref      TEXT,
    enabled         BOOLEAN NOT NULL DEFAULT true,
    last_used_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID,
    updated_by      UUID,
    version         INT NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'ACTIVE'
                    CHECK (status IN ('ACTIVE','DISABLED')),
    audit_reference TEXT,
    deleted_at      TIMESTAMPTZ,
    deleted_by      UUID,
    deletion_reason TEXT
);

CREATE INDEX idx_user_mfa_user ON user_mfa (user_id);

SELECT ehos_make_history('user_mfa');

-- ---------------------------------------------------------------------------
-- user_sessions
-- ---------------------------------------------------------------------------
CREATE TABLE user_sessions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES users(id),
    refresh_token_id UUID,
    client_id        TEXT NOT NULL,
    ip_address       INET,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at     TIMESTAMPTZ,
    ended_at         TIMESTAMPTZ,
    revoked          BOOLEAN NOT NULL DEFAULT false,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    version          INT NOT NULL DEFAULT 1,
    status           TEXT NOT NULL DEFAULT 'ACTIVE'
                     CHECK (status IN ('ACTIVE','EXPIRED','REVOKED','ENDED')),
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason  TEXT
);

CREATE INDEX idx_user_sessions_user ON user_sessions (user_id);
CREATE INDEX idx_user_sessions_refresh_token ON user_sessions (refresh_token_id);

SELECT ehos_make_history('user_sessions');

COMMIT;

-- ---------------------------------------------------------------------------
-- application role grants
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO ehos_identity_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_identity_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_identity_app;