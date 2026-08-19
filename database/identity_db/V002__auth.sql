-- ============================================================================
-- EHOS  identity_db/V002__auth.sql
-- authentication-service: password fields, MFA encryption, refresh tokens,
-- RBAC (roles/permissions), ABAC policies, password history, and auth audit log.
--
-- V001 mirrored Keycloak; V002 converts identity_db into the source of truth
-- for the authentication-service (AUTHENTICATION.md migration path). Applies on
-- top of V001__init.sql; shared files (02_history_trigger, 03_outbox) already
-- exist. Follows DATABASE_DESIGN.md conventions 2.5/2.6/2.7/2.8 and 9.
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- users: add password + account-state columns
-- ---------------------------------------------------------------------------
ALTER TABLE users ADD COLUMN password_hash      TEXT;                 -- bcrypt, never plaintext
ALTER TABLE users ADD COLUMN failed_attempts    INT  NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN locked_until       TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN password_changed_at TIMESTAMPTZ;

-- ---------------------------------------------------------------------------
-- user_mfa: encrypted secret storage + per-method uniqueness
-- ---------------------------------------------------------------------------
ALTER TABLE user_mfa ADD COLUMN secret_encrypted TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_mfa_user_method ON user_mfa (user_id, method);

-- ---------------------------------------------------------------------------
-- user_sessions: capture user agent
-- ---------------------------------------------------------------------------
ALTER TABLE user_sessions ADD COLUMN user_agent TEXT;

-- ---------------------------------------------------------------------------
-- refresh_tokens : opaque, stored as SHA-256 hash; rotates within a family
-- ---------------------------------------------------------------------------
CREATE TABLE refresh_tokens (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL REFERENCES users(id),
    session_id        UUID REFERENCES user_sessions(id),
    token_hash        TEXT NOT NULL,
    family_id         UUID NOT NULL,
    parent_token_hash TEXT,
    client_id         TEXT NOT NULL DEFAULT 'ehos-api',
    ip_address        INET,
    user_agent        TEXT,
    expires_at        TIMESTAMPTZ NOT NULL,
    revoked_at        TIMESTAMPTZ,
    replaced_by       UUID,
    reuse_detected    BOOLEAN NOT NULL DEFAULT false,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by        UUID,
    updated_by        UUID,
    version           INT NOT NULL DEFAULT 1,
    status            TEXT NOT NULL DEFAULT 'ACTIVE'
                      CHECK (status IN ('ACTIVE','ROTATED','REVOKED','EXPIRED')),
    audit_reference   TEXT,
    deleted_at        TIMESTAMPTZ,
    deleted_by        UUID,
    deletion_reason   TEXT
);

CREATE UNIQUE INDEX uq_refresh_tokens_hash ON refresh_tokens (token_hash);
CREATE INDEX idx_refresh_tokens_user ON refresh_tokens (user_id);
CREATE INDEX idx_refresh_tokens_family ON refresh_tokens (family_id);
CREATE INDEX idx_refresh_tokens_session ON refresh_tokens (session_id);

SELECT ehos_make_history('refresh_tokens');

-- ---------------------------------------------------------------------------
-- roles / permissions / assignments (RBAC)
-- ---------------------------------------------------------------------------
CREATE TABLE roles (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code             TEXT NOT NULL,
    name             TEXT NOT NULL,
    description      TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    version          INT NOT NULL DEFAULT 1,
    status           TEXT NOT NULL DEFAULT 'ACTIVE'
                     CHECK (status IN ('ACTIVE','DISABLED')),
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason  TEXT
);

CREATE UNIQUE INDEX uq_roles_code ON roles (code) WHERE deleted_at IS NULL;

SELECT ehos_make_history('roles');

CREATE TABLE permissions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code             TEXT NOT NULL,
    resource         TEXT NOT NULL,
    action           TEXT NOT NULL,
    description      TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    version          INT NOT NULL DEFAULT 1,
    status           TEXT NOT NULL DEFAULT 'ACTIVE'
                     CHECK (status IN ('ACTIVE','DISABLED')),
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason  TEXT
);

CREATE UNIQUE INDEX uq_permissions_code ON permissions (code) WHERE deleted_at IS NULL;
CREATE INDEX idx_permissions_resource ON permissions (resource, action);

SELECT ehos_make_history('permissions');

CREATE TABLE user_roles (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES users(id),
    role_id          UUID NOT NULL REFERENCES roles(id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    version          INT NOT NULL DEFAULT 1,
    status           TEXT NOT NULL DEFAULT 'ACTIVE',
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason  TEXT
);

CREATE UNIQUE INDEX uq_user_roles_user_role ON user_roles (user_id, role_id);
CREATE INDEX idx_user_roles_role ON user_roles (role_id);

CREATE TABLE role_permissions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id          UUID NOT NULL REFERENCES roles(id),
    permission_id    UUID NOT NULL REFERENCES permissions(id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    version          INT NOT NULL DEFAULT 1,
    status           TEXT NOT NULL DEFAULT 'ACTIVE',
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason  TEXT
);

CREATE UNIQUE INDEX uq_role_permissions_role_perm ON role_permissions (role_id, permission_id);
CREATE INDEX idx_role_permissions_perm ON role_permissions (permission_id);

-- ---------------------------------------------------------------------------
-- abac_policies : attribute-based access control rules
-- ---------------------------------------------------------------------------
CREATE TABLE abac_policies (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code             TEXT NOT NULL,
    description      TEXT,
    resource         TEXT NOT NULL,
    action           TEXT NOT NULL,
    effect           TEXT NOT NULL CHECK (effect IN ('allow','deny')),
    conditions       JSONB,
    priority         INT NOT NULL DEFAULT 0,
    enabled          BOOLEAN NOT NULL DEFAULT true,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    version          INT NOT NULL DEFAULT 1,
    status           TEXT NOT NULL DEFAULT 'ACTIVE',
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason  TEXT
);

CREATE UNIQUE INDEX uq_abac_policies_code ON abac_policies (code) WHERE deleted_at IS NULL;
CREATE INDEX idx_abac_policies_resource ON abac_policies (resource, action);

-- ---------------------------------------------------------------------------
-- password_history : recent hashes for reuse policy
-- ---------------------------------------------------------------------------
CREATE TABLE password_history (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES users(id),
    password_hash    TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    version          INT NOT NULL DEFAULT 1,
    status           TEXT NOT NULL DEFAULT 'ACTIVE',
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason  TEXT
);

CREATE INDEX idx_password_history_user ON password_history (user_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- auth_events : immutable audit log of authentication activity
-- ---------------------------------------------------------------------------
CREATE TABLE auth_events (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID REFERENCES users(id),
    event_type       TEXT NOT NULL,
    result           TEXT NOT NULL CHECK (result IN ('success','failure')),
    ip_address       INET,
    user_agent       TEXT,
    details          JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    version          INT NOT NULL DEFAULT 1,
    status           TEXT NOT NULL DEFAULT 'ACTIVE',
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason  TEXT
);

CREATE INDEX idx_auth_events_user ON auth_events (user_id, created_at DESC);
CREATE INDEX idx_auth_events_type ON auth_events (event_type, created_at DESC);

SELECT ehos_make_history('auth_events');

COMMIT;

-- ---------------------------------------------------------------------------
-- application role grants for the new tables
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO ehos_identity_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_identity_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_identity_app;