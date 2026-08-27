-- ============================================================================
-- EHOS  insurance_db  V001__init.sql
-- insurance-service: coverage, claims, prior authorizations.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- coverage — patient insurance coverage
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS coverage (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id     UUID NOT NULL,
    payer_name     VARCHAR NOT NULL,
    plan_name      VARCHAR,
    policy_number  VARCHAR NOT NULL,
    group_number   VARCHAR,
    coverage_type  VARCHAR NOT NULL,
    effective_date VARCHAR NOT NULL,
    termination_date VARCHAR,
    copay          DOUBLE PRECISION,
    deductible     DOUBLE PRECISION,
    coinsurance    DOUBLE PRECISION,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by     UUID,
    updated_by     UUID,
    model_version  INTEGER NOT NULL DEFAULT 1,
    status         VARCHAR NOT NULL,
    audit_reference VARCHAR,
    deleted_at     TIMESTAMPTZ,
    deleted_by     UUID,
    deletion_reason TEXT,
    CONSTRAINT ck_coverage_type CHECK (coverage_type IN ('HEALTH','DENTAL','VISION','PRESCRIPTION','MENTAL_HEALTH'))
);

CREATE INDEX IF NOT EXISTS idx_coverage_patient ON coverage(patient_id, is_active);

-- ----------------------------------------------------------------------------
-- claims — insurance claim lifecycle
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS claims (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id     UUID NOT NULL,
    coverage_id    UUID NOT NULL,
    encounter_id   UUID,
    service_date   VARCHAR NOT NULL,
    diagnosis_codes JSON,
    procedure_codes JSON,
    total_amount   DOUBLE PRECISION NOT NULL,
    approved_amount DOUBLE PRECISION,
    paid_amount    DOUBLE PRECISION,
    patient_responsibility DOUBLE PRECISION,
    status         VARCHAR NOT NULL DEFAULT 'DRAFT',
    denial_reason  TEXT,
    submitted_at   TIMESTAMPTZ,
    adjudicated_at TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by     UUID,
    updated_by     UUID,
    model_version  INTEGER NOT NULL DEFAULT 1,
    audit_reference VARCHAR,
    deleted_at     TIMESTAMPTZ,
    deleted_by     UUID,
    deletion_reason TEXT,
    CONSTRAINT ck_claim_status CHECK (status IN ('DRAFT','SUBMITTED','REVIEWING','APPROVED','PARTIAL','DENIED','APPEALED','PAID','VOID'))
);

CREATE INDEX IF NOT EXISTS idx_claims_patient ON claims(patient_id, created_at);
CREATE INDEX IF NOT EXISTS idx_claims_coverage ON claims(coverage_id);

-- ----------------------------------------------------------------------------
-- prior_authorizations — pre-service insurance approvals
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prior_authorizations (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id     UUID NOT NULL,
    coverage_id    UUID NOT NULL,
    service_type   VARCHAR NOT NULL,
    procedure_codes JSON,
    clinical_justification TEXT,
    requested_by   UUID NOT NULL,
    status         VARCHAR NOT NULL DEFAULT 'PENDING',
    decision       VARCHAR,
    approved_units INTEGER,
    valid_from     VARCHAR,
    valid_to       VARCHAR,
    decided_by     UUID,
    decided_at     TIMESTAMPTZ,
    denial_reason  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by     UUID,
    updated_by     UUID,
    model_version  INTEGER NOT NULL DEFAULT 1,
    audit_reference VARCHAR,
    deleted_at     TIMESTAMPTZ,
    deleted_by     UUID,
    deletion_reason TEXT,
    CONSTRAINT ck_pauth_status CHECK (status IN ('PENDING','SUBMITTED','APPROVED','DENIED','EXPIRED','CANCELLED'))
);

CREATE INDEX IF NOT EXISTS idx_pauth_patient ON prior_authorizations(patient_id);

-- ----------------------------------------------------------------------------
-- history tables
-- ----------------------------------------------------------------------------
SELECT ehos_make_history('coverage');
SELECT ehos_make_history('claims');
SELECT ehos_make_history('prior_authorizations');

-- ----------------------------------------------------------------------------
-- grants
-- ----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO ehos_insurance_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_insurance_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_insurance_app;

COMMIT;