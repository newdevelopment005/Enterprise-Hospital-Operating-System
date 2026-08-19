-- ============================================================================
-- EHOS  patient_db / V002__registration_features.sql
-- Service: patient-service
-- Description: Extends the patient master with registration/operations features:
--   structured addresses, insurance-card snapshot, medical alerts, photos,
--   biometrics readiness, merge support (merged_into pointer) and an explicit
--   patient timeline (audited, source-tagged events). V001 kept contact info in
--   JSONB; this migration normalizes the operational records while leaving the
--   validated MPI core untouched.
-- Design: DATABASE_DESIGN.md sections 2 and 5.1; conventions 2.5/2.6/2.7/2.8/9.
-- Requires: V001__init.sql applied first (patients exists, shared helpers exist).
-- App role: ehos_patient_app. RLS mirrors V001 (PHI tables).
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- patients : support merge (a record can be merged INTO another) and a
-- lightweight biometrics-ready flag
-- ---------------------------------------------------------------------------
ALTER TABLE patients ADD COLUMN merged_into_id UUID REFERENCES patients(id);
ALTER TABLE patients ADD COLUMN biometrics_ready BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX idx_patients_merged_into ON patients (merged_into_id) WHERE merged_into_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- patient_addresses : structured addresses (home, work, billing, next-of-kin)
-- ---------------------------------------------------------------------------
CREATE TABLE patient_addresses (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id    UUID NOT NULL REFERENCES patients(id),
    address_type  TEXT NOT NULL CHECK (address_type IN ('HOME','WORK','BILLING','CONTACT')),
    line1         TEXT,
    line2         TEXT,
    city          TEXT,
    state_province TEXT,
    postal_code   TEXT,
    country       TEXT DEFAULT 'TZ',
    is_primary    BOOLEAN NOT NULL DEFAULT false,
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

CREATE INDEX idx_patient_addresses_patient ON patient_addresses (patient_id);

SELECT ehos_make_history('patient_addresses');

-- ---------------------------------------------------------------------------
-- patient_insurance : insurance-card snapshot captured at registration.
-- Authoritative policy/coverage lifecycle remains in insurance_db
-- (patient_insurance_policies); this is the read-side registration card data.
-- ---------------------------------------------------------------------------
CREATE TABLE patient_insurance (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id         UUID NOT NULL REFERENCES patients(id),
    provider_name      TEXT NOT NULL,
    provider_code      TEXT,
    card_number        TEXT,
    policy_number      TEXT,
    member_number      TEXT,
    relation_to_subscriber TEXT CHECK (relation_to_subscriber IN ('SELF','SPOUSE','DEPENDENT','OTHER')),
    coverage_type      TEXT CHECK (coverage_type IN ('INPATIENT','OUTPATIENT','DENTAL','OPTICAL','MATERNITY','SURGERY','COMBO')),
    valid_from         DATE,
    valid_to           DATE,
    remarks            TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by         UUID,
    updated_by         UUID,
    version            INT NOT NULL DEFAULT 1,
    status             TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','EXPIRED','CANCELLED')),
    audit_reference    TEXT,
    deleted_at         TIMESTAMPTZ,
    deleted_by         UUID,
    deletion_reason    TEXT
);

CREATE INDEX idx_patient_insurance_patient ON patient_insurance (patient_id);
CREATE INDEX idx_patient_insurance_provider ON patient_insurance (provider_code, card_number);
CREATE UNIQUE INDEX uq_patient_insurance_card ON patient_insurance (patient_id, card_number)
    WHERE card_number IS NOT NULL AND deleted_at IS NULL;

SELECT ehos_make_history('patient_insurance');

-- ---------------------------------------------------------------------------
-- medical_alerts : allergies, critical conditions, fall-risk, etc.
-- ---------------------------------------------------------------------------
CREATE TABLE medical_alerts (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id    UUID NOT NULL REFERENCES patients(id),
    alert_type    TEXT NOT NULL CHECK (alert_type IN ('ALLERGY','CONDITION','FALL_RISK','LATE_CREATION',
                                                      'DRUG_SENSITIVITY','INFECTION','OTHER')),
    severity      TEXT NOT NULL CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    title         TEXT NOT NULL,
    description   TEXT,
    active        BOOLEAN NOT NULL DEFAULT true,
    resolved_at   TIMESTAMPTZ,
    resolved_by   UUID,
    resolved_reason TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by    UUID,
    updated_by    UUID,
    version       INT NOT NULL DEFAULT 1,
    status        TEXT NOT NULL DEFAULT 'ACTIVE',
    audit_reference TEXT,
    deleted_at    TIMESTAMPTZ,
    deleted_by    UUID,
    deletion_reason TEXT
);

CREATE INDEX idx_medical_alerts_patient ON medical_alerts (patient_id);
CREATE INDEX idx_medical_alerts_active ON medical_alerts (patient_id, active) WHERE deleted_at IS NULL;

SELECT ehos_make_history('medical_alerts');

-- ---------------------------------------------------------------------------
-- patient_photos : photographs (passport, profile). Bytea stores the image for
-- the small-footprint deployment; production may switch to object-store refs.
-- ---------------------------------------------------------------------------
CREATE TABLE patient_photos (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id   UUID NOT NULL REFERENCES patients(id),
    photo        BYTEA,
    object_ref   TEXT,
    content_type TEXT NOT NULL DEFAULT 'image/jpeg',
    width        INT,
    height       INT,
    is_primary   BOOLEAN NOT NULL DEFAULT false,
    taken_at     TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by   UUID,
    updated_by   UUID,
    version      INT NOT NULL DEFAULT 1,
    status       TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','ARCHIVED')),
    audit_reference TEXT,
    deleted_at   TIMESTAMPTZ,
    deleted_by   UUID,
    deletion_reason TEXT
);

CREATE INDEX idx_patient_photos_patient ON patient_photos (patient_id);

SELECT ehos_make_history('patient_photos');

-- ALTER TABLE patients ENABLE ROW LEVEL SECURITY -- RLS already enabled in V001

-- ---------------------------------------------------------------------------
-- patient_biometrics : biometric readiness registry (fingerprint/face/iris)
-- Only stores a reference/status, never raw biometric templates in this DB.
-- ---------------------------------------------------------------------------
CREATE TABLE patient_biometrics (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id   UUID NOT NULL REFERENCES patients(id),
    modality     TEXT NOT NULL CHECK (modality IN ('FINGERPRINT','FACE','IRIS','VOICE')),
    enrollment_state TEXT NOT NULL DEFAULT 'ENROLLED'
                     CHECK (enrollment_state IN ('PLANNED','ENROLLED','READY','FAILED','DISABLED')),
    provider     TEXT,
    template_ref TEXT,
    enrolled_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by   UUID,
    updated_by   UUID,
    version      INT NOT NULL DEFAULT 1,
    status       TEXT NOT NULL DEFAULT 'ACTIVE',
    audit_reference TEXT,
    deleted_at   TIMESTAMPTZ,
    deleted_by   UUID,
    deletion_reason TEXT
);

CREATE INDEX idx_patient_biometrics_patient ON patient_biometrics (patient_id);
CREATE UNIQUE INDEX uq_patient_biometrics_patient_modality
    ON patient_biometrics (patient_id, modality) WHERE deleted_at IS NULL;

SELECT ehos_make_history('patient_biometrics');

-- ---------------------------------------------------------------------------
-- patient_timeline : source-tagged, audited event timeline (registration,
-- updates, alerts, merges, identifiers). Write-only log; wraps history.
-- ---------------------------------------------------------------------------
CREATE TABLE patient_timeline (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id     UUID NOT NULL REFERENCES patients(id),
    event_type     TEXT NOT NULL CHECK (event_type IN ('REGISTERED','UPDATED','ALERT_ADDED','ALERT_RESOLVED',
                                                       'MERGED_INTO','PHOTO_ADDED','BIOMETRICS_ENROLLED',
                                                       'IDENTIFIER_ADDED','CONTACT_ADDED','INSURANCE_ADDED',
                                                       'CONSENT_GIVEN','ADDRESS_ADDED')),
    source         TEXT NOT NULL DEFAULT 'patient-service',
    reference_id   UUID,
    occurred_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor          UUID,
    details        JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by     UUID,
    updated_by     UUID,
    version        INT NOT NULL DEFAULT 1,
    status         TEXT NOT NULL DEFAULT 'ACTIVE',
    audit_reference TEXT,
    deleted_at     TIMESTAMPTZ,
    deleted_by     UUID,
    deletion_reason TEXT
);

CREATE INDEX idx_patient_timeline_patient ON patient_timeline (patient_id, occurred_at DESC);
CREATE INDEX idx_patient_timeline_type ON patient_timeline (event_type, occurred_at DESC);

SELECT ehos_make_history('patient_timeline');

-- ---------------------------------------------------------------------------
-- RLS for the new PHI tables (mirrors V001 pattern: app role, no hard delete)
-- RLS is already enabled on patients/identifiers/consents in V001.
-- ---------------------------------------------------------------------------
ALTER TABLE patient_addresses ENABLE ROW LEVEL SECURITY;
ALTER TABLE patient_insurance ENABLE ROW LEVEL SECURITY;
ALTER TABLE medical_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE patient_photos ENABLE ROW LEVEL SECURITY;
ALTER TABLE patient_biometrics ENABLE ROW LEVEL SECURITY;

CREATE POLICY patient_addresses_select ON patient_addresses
    FOR SELECT TO ehos_patient_app USING (deleted_at IS NULL);
CREATE POLICY patient_addresses_insert ON patient_addresses
    FOR INSERT TO ehos_patient_app WITH CHECK (true);
CREATE POLICY patient_addresses_update ON patient_addresses
    FOR UPDATE TO ehos_patient_app USING (deleted_at IS NULL) WITH CHECK (deleted_at IS NULL);

CREATE POLICY patient_insurance_select ON patient_insurance
    FOR SELECT TO ehos_patient_app USING (deleted_at IS NULL);
CREATE POLICY patient_insurance_insert ON patient_insurance
    FOR INSERT TO ehos_patient_app WITH CHECK (true);
CREATE POLICY patient_insurance_update ON patient_insurance
    FOR UPDATE TO ehos_patient_app USING (deleted_at IS NULL) WITH CHECK (deleted_at IS NULL);

CREATE POLICY medical_alerts_select ON medical_alerts
    FOR SELECT TO ehos_patient_app USING (deleted_at IS NULL);
CREATE POLICY medical_alerts_insert ON medical_alerts
    FOR INSERT TO ehos_patient_app WITH CHECK (true);
CREATE POLICY medical_alerts_update ON medical_alerts
    FOR UPDATE TO ehos_patient_app USING (deleted_at IS NULL) WITH CHECK (deleted_at IS NULL);

CREATE POLICY patient_photos_select ON patient_photos
    FOR SELECT TO ehos_patient_app USING (deleted_at IS NULL);
CREATE POLICY patient_photos_insert ON patient_photos
    FOR INSERT TO ehos_patient_app WITH CHECK (true);
CREATE POLICY patient_photos_update ON patient_photos
    FOR UPDATE TO ehos_patient_app USING (deleted_at IS NULL) WITH CHECK (deleted_at IS NULL);

CREATE POLICY patient_biometrics_select ON patient_biometrics
    FOR SELECT TO ehos_patient_app USING (deleted_at IS NULL);
CREATE POLICY patient_biometrics_insert ON patient_biometrics
    FOR INSERT TO ehos_patient_app WITH CHECK (true);
CREATE POLICY patient_biometrics_update ON patient_biometrics
    FOR UPDATE TO ehos_patient_app USING (deleted_at IS NULL) WITH CHECK (deleted_at IS NULL);

GRANT USAGE ON SCHEMA public TO ehos_patient_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_patient_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_patient_app;

COMMIT;