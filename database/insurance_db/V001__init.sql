-- ============================================================================
-- EHOS  insurance_db / V001__init.sql
-- Service: insurance-service
-- Description: Baseline schema for the insurance database: insurance providers,
--   patient insurance policies, coverage verifications and claims.
-- Design: DATABASE_DESIGN.md sections 2, 7.2, 9, 10.
-- Requires: shared 01_extensions.sql (pgcrypto, pg_trgm), 02_history_trigger.sql
--   (fn_append_history(), ehos_make_history()), 03_outbox.sql (outbox_events)
--   applied first by apply.py. No \i includes in this file.
-- Postgres 16+, lowercase snake_case, app role: ehos_insurance_app.
-- ============================================================================

BEGIN;

CREATE TABLE insurance_providers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code        TEXT NOT NULL,
    name        TEXT NOT NULL,
    contact     JSONB,
    is_active   BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by  UUID,
    updated_by  UUID,
    version     INT NOT NULL DEFAULT 1,
    status      TEXT NOT NULL,
    audit_reference TEXT,
    deleted_at  TIMESTAMPTZ,
    deleted_by  UUID,
    deletion_reason TEXT
);

CREATE UNIQUE INDEX uq_insurance_providers_code ON insurance_providers (code) WHERE deleted_at IS NULL;

SELECT ehos_make_history('insurance_providers');

CREATE TABLE patient_insurance_policies (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id       UUID NOT NULL,
    provider_id      UUID NOT NULL REFERENCES insurance_providers(id),
    policy_number    TEXT NOT NULL,
    insured_progeny  TEXT,
    coverage_type    TEXT,
    valid_from       DATE NOT NULL,
    valid_to         DATE,
    attributes       JSONB,
    status           TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','SUSPENDED','EXPIRED','CANCELLED')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    version          INT NOT NULL DEFAULT 1,
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason  TEXT
);

CREATE INDEX idx_policies_patient ON patient_insurance_policies (patient_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_policies_provider ON patient_insurance_policies (provider_id);

SELECT ehos_make_history('patient_insurance_policies');

CREATE TABLE coverage_verifications (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_id        UUID NOT NULL REFERENCES patient_insurance_policies(id),
    service_category TEXT,
    verified_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    verified_by      UUID,
    result           JSONB NOT NULL,
    coverage_percent NUMERIC(5,2),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    version          INT NOT NULL DEFAULT 1,
    status           TEXT NOT NULL,
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason  TEXT
);

CREATE INDEX idx_coverage_policy ON coverage_verifications (policy_id);

SELECT ehos_make_history('coverage_verifications');

CREATE TABLE claims (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_number     TEXT NOT NULL,
    patient_id       UUID NOT NULL,
    policy_id        UUID REFERENCES patient_insurance_policies(id),
    invoice_id       UUID,
    amount           NUMERIC(12,2) NOT NULL,
    status           TEXT NOT NULL DEFAULT 'DRAFT'
                     CHECK (status IN ('DRAFT','SUBMITTED','IN_REVIEW','APPROVED','DENIED','PAID','REJECTED','REOPENED')),
    submitted_at     TIMESTAMPTZ,
    submitted_by     UUID,
    provider_response JSONB,
    paid_amount      NUMERIC(12,2),
    denial_reason    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    version          INT NOT NULL DEFAULT 1,
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason  TEXT
);

CREATE UNIQUE INDEX uq_claims_claim_number ON claims (claim_number) WHERE deleted_at IS NULL;
CREATE INDEX idx_claims_patient ON claims (patient_id, status) WHERE deleted_at IS NULL;
CREATE INDEX idx_claims_policy ON claims (policy_id);

SELECT ehos_make_history('claims');

GRANT USAGE ON SCHEMA public TO ehos_insurance_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_insurance_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_insurance_app;

COMMIT;