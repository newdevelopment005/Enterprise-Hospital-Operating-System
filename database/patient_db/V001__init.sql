-- ============================================================================
-- EHOS  patient_db / V001__init.sql
-- Service: patient-service
-- Description: Baseline schema for the patient master database: the MPI
--   patients entity plus patient_identifiers (multi-issuer), patient_contacts,
--   patient_consents and patient_links (record linkage), with per-table history
--   triggers and RLS on the PHI tables.
-- Design: DATABASE_DESIGN.md sections 2, 5.1, 2.11, 9, 10.
-- Requires: shared 01_extensions.sql (pgcrypto, pg_trgm), 02_history_trigger.sql
--   (fn_append_history(), ehos_make_history()), 03_outbox.sql (outbox_events)
--   applied first by apply.py. No \i includes in this file.
-- Postgres 16+, lowercase snake_case, app role: ehos_patient_app.
-- ============================================================================

BEGIN;

CREATE TABLE patients (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_number         TEXT,
    mrn                    TEXT,
    first_name             TEXT NOT NULL,
    last_name              TEXT NOT NULL,
    other_names            TEXT,
    date_of_birth          DATE,
    gender                 TEXT CHECK (gender IN ('MALE','FEMALE','OTHER','UNDISCLOSED')),
    blood_group            TEXT CHECK (blood_group IN ('A+','A-','B+','B-','AB+','AB-','O+','O-')),
    nationality            TEXT,
    marital_status         TEXT,
    language_pref          TEXT DEFAULT 'en',
    national_identifier    TEXT,
    contact_info           JSONB,
    address                JSONB,
    emergency_contact      JSONB,
    registration_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    consent_summary        JSONB,
    deceased_at            TIMESTAMPTZ,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by             UUID,
    updated_by             UUID,
    version                INT NOT NULL DEFAULT 1,
    status                 TEXT NOT NULL,
    audit_reference        TEXT,
    deleted_at             TIMESTAMPTZ,
    deleted_by             UUID,
    deletion_reason        TEXT
);

CREATE UNIQUE INDEX uq_patients_mrn ON patients (mrn) WHERE mrn IS NOT NULL;
CREATE UNIQUE INDEX uq_patients_patient_number ON patients (patient_number) WHERE patient_number IS NOT NULL;
CREATE INDEX idx_patients_name_trgm ON patients USING gin (first_name gin_trgm_ops, last_name gin_trgm_ops);
CREATE INDEX idx_patients_dob ON patients (date_of_birth) WHERE deleted_at IS NULL;
CREATE INDEX idx_patients_mrn_trgm ON patients USING gin (mrn gin_trgm_ops);

SELECT ehos_make_history('patients');

CREATE TABLE patient_identifiers (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id       UUID NOT NULL REFERENCES patients(id),
    identifier_type  TEXT NOT NULL,
    identifier_value TEXT NOT NULL,
    issuer           TEXT,
    valid_from       DATE,
    valid_to         DATE,
    is_primary       BOOLEAN NOT NULL DEFAULT false,
    encrypted_value  BYTEA,
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

CREATE UNIQUE INDEX uq_patient_identifiers_type_issuer_value
    ON patient_identifiers (identifier_type, issuer, identifier_value)
    WHERE deleted_at IS NULL;
CREATE INDEX idx_patient_identifiers_patient ON patient_identifiers (patient_id);

SELECT ehos_make_history('patient_identifiers');

CREATE TABLE patient_contacts (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id    UUID NOT NULL REFERENCES patients(id),
    contact_type  TEXT NOT NULL CHECK (contact_type IN ('PHONE','EMAIL','WHATSAPP','EMERGENCY')),
    value         TEXT NOT NULL,
    is_primary    BOOLEAN NOT NULL DEFAULT false,
    is_verified   BOOLEAN NOT NULL DEFAULT false,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by    UUID,
    updated_by    UUID,
    version       INT NOT NULL DEFAULT 1,
    status        TEXT NOT NULL,
    audit_reference TEXT,
    deleted_at    TIMESTAMPTZ,
    deleted_by    UUID,
    deletion_reason TEXT
);

CREATE UNIQUE INDEX uq_patient_contacts_patient_type_value
    ON patient_contacts (patient_id, contact_type, value)
    WHERE deleted_at IS NULL;
CREATE INDEX idx_patient_contacts_patient ON patient_contacts (patient_id);

SELECT ehos_make_history('patient_contacts');

CREATE TABLE patient_consents (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id        UUID NOT NULL REFERENCES patients(id),
    consent_type      TEXT NOT NULL CHECK (consent_type IN ('TREATMENT','DATA_SHARING','RESEARCH','TELEHEALTH','AUTOMATION')),
    granted           BOOLEAN NOT NULL,
    date_given        DATE NOT NULL DEFAULT CURRENT_DATE,
    expiry_date       DATE,
    documentation_ref TEXT,
    withdrawn_at      TIMESTAMPTZ,
    withdrawn_by      UUID,
    revoked_reason    TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by        UUID,
    updated_by        UUID,
    version           INT NOT NULL DEFAULT 1,
    status            TEXT NOT NULL,
    audit_reference   TEXT,
    deleted_at        TIMESTAMPTZ,
    deleted_by        UUID,
    deletion_reason   TEXT
);

CREATE INDEX idx_patient_consents_patient ON patient_consents (patient_id);

SELECT ehos_make_history('patient_consents');

CREATE TABLE patient_links (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    left_patient_id   UUID NOT NULL REFERENCES patients(id),
    right_patient_id  UUID NOT NULL REFERENCES patients(id),
    match_score       NUMERIC(5,4),
    match_method      TEXT,
    link_type         TEXT NOT NULL CHECK (link_type IN ('SAME_PERSON','DUPLICATE','RELATED')),
    resolved_by       UUID,
    resolved_at       TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by        UUID,
    updated_by        UUID,
    version           INT NOT NULL DEFAULT 1,
    status            TEXT NOT NULL,
    audit_reference   TEXT,
    deleted_at        TIMESTAMPTZ,
    deleted_by        UUID,
    deletion_reason   TEXT,
    CHECK (left_patient_id <> right_patient_id)
);

CREATE INDEX idx_patient_links_left ON patient_links (left_patient_id);
CREATE INDEX idx_patient_links_right ON patient_links (right_patient_id);

SELECT ehos_make_history('patient_links');

ALTER TABLE patients ENABLE ROW LEVEL SECURITY;
ALTER TABLE patient_identifiers ENABLE ROW LEVEL SECURITY;
ALTER TABLE patient_consents ENABLE ROW LEVEL SECURITY;

CREATE POLICY patients_select ON patients
    FOR SELECT TO ehos_patient_app USING (deleted_at IS NULL);
CREATE POLICY patients_insert ON patients
    FOR INSERT TO ehos_patient_app WITH CHECK (true);
CREATE POLICY patients_update ON patients
    FOR UPDATE TO ehos_patient_app USING (deleted_at IS NULL) WITH CHECK (deleted_at IS NULL);
CREATE POLICY patients_delete ON patients
    FOR DELETE TO ehos_patient_app USING (false);

CREATE POLICY patient_identifiers_select ON patient_identifiers
    FOR SELECT TO ehos_patient_app USING (deleted_at IS NULL);
CREATE POLICY patient_identifiers_insert ON patient_identifiers
    FOR INSERT TO ehos_patient_app WITH CHECK (true);
CREATE POLICY patient_identifiers_update ON patient_identifiers
    FOR UPDATE TO ehos_patient_app USING (deleted_at IS NULL) WITH CHECK (deleted_at IS NULL);
CREATE POLICY patient_identifiers_delete ON patient_identifiers
    FOR DELETE TO ehos_patient_app USING (false);

CREATE POLICY patient_consents_select ON patient_consents
    FOR SELECT TO ehos_patient_app USING (deleted_at IS NULL);
CREATE POLICY patient_consents_insert ON patient_consents
    FOR INSERT TO ehos_patient_app WITH CHECK (true);
CREATE POLICY patient_consents_update ON patient_consents
    FOR UPDATE TO ehos_patient_app USING (deleted_at IS NULL) WITH CHECK (deleted_at IS NULL);
CREATE POLICY patient_consents_delete ON patient_consents
    FOR DELETE TO ehos_patient_app USING (false);

GRANT USAGE ON SCHEMA public TO ehos_patient_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_patient_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_patient_app;

COMMIT;