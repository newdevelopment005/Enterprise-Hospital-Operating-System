-- ============================================================================
-- EHOS  prescription_db/V001__init.sql
-- Service:      prescription-service
-- Description:  Medication prescribing: prescription headers with allergy/use
--               interaction flags, per-item medication lines, medication
--               administration records, and patient allergy records. RLS on PHI.
-- Design refs:  DATABASE_DESIGN.md sections 2.5, 2.6, 2.7, 2.8, 2.11, 6.3, 9, 10
-- NOTE: Shared objects (pgcrypto, pg_trgm, fn_append_history(),
--       ehos_make_history(), outbox_events) are applied BEFORE this file by
--       apply.py and are NOT re-created here.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- prescriptions
-- ----------------------------------------------------------------------------
CREATE TABLE prescriptions (
    id                   uuid primary key default gen_random_uuid(),
    patient_id           uuid not null,     -- cross-db ref to patient-service (no FK)
    patient_snapshot     jsonb,
    encounter_id         uuid,              -- cross-db ref to ehr-service (no FK)
    prescriber_id        uuid not null,     -- cross-db ref to hr-service (no FK)
    issue_date           date not null default current_date,
    therapy_type         text check (therapy_type in ('ACUTE','CHRONIC','PRN','PROPHYLACTIC')),
    allergy_checked      boolean not null default false,
    interaction_checked  boolean not null default false,
    start_date           date,
    end_date             date,
    repeat_instructions  text,
    reason               text,
    cancelled_by         uuid,
    cancelled_at         timestamptz,
    cancellation_reason  text,
    created_at           timestamptz not null default now(),
    updated_at           timestamptz not null default now(),
    created_by           uuid,
    updated_by           uuid,
    version              int not null default 1,
    status               text not null default 'ACTIVE' check (status in ('ACTIVE','PAUSED','COMPLETED','CANCELLED','EXPIRED')),
    audit_reference      text,
    deleted_at           timestamptz,
    deleted_by           uuid,
    deletion_reason      text
);

CREATE INDEX idx_prescriptions_patient ON prescriptions (patient_id, issue_date DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_prescriptions_status ON prescriptions (status);

ALTER TABLE prescriptions ENABLE ROW LEVEL SECURITY;
CREATE POLICY prescriptions_select ON prescriptions FOR SELECT TO ehos_prescription_app USING (deleted_at IS NULL);
CREATE POLICY prescriptions_insert ON prescriptions FOR INSERT TO ehos_prescription_app WITH CHECK (true);
CREATE POLICY prescriptions_update ON prescriptions FOR UPDATE TO ehos_prescription_app USING (deleted_at IS NULL);
CREATE POLICY prescriptions_delete ON prescriptions FOR DELETE TO ehos_prescription_app USING (false);

SELECT ehos_make_history('prescriptions');

-- ----------------------------------------------------------------------------
-- prescription_items
-- ----------------------------------------------------------------------------
CREATE TABLE prescription_items (
    id              uuid primary key default gen_random_uuid(),
    prescription_id uuid not null references prescriptions(id),
    medication_id   uuid,                   -- cross-db ref to pharmacy catalog (no FK)
    medication      text not null,
    dosage          text not null,
    frequency       text not null,
    route           text,
    duration_days   int,
    quantity        numeric,
    instructions    text,
    max_per_day     numeric,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    created_by      uuid,
    updated_by      uuid,
    version         int not null default 1,
    status          text not null default 'ACTIVE' check (status in ('ACTIVE','PAUSED','COMPLETED','CANCELLED','DISCONTINUED')),
    audit_reference text,
    deleted_at      timestamptz,
    deleted_by      uuid,
    deletion_reason text
);

CREATE INDEX idx_rx_items_prescription ON prescription_items (prescription_id);

ALTER TABLE prescription_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY prescription_items_select ON prescription_items FOR SELECT TO ehos_prescription_app USING (deleted_at IS NULL);
CREATE POLICY prescription_items_insert ON prescription_items FOR INSERT TO ehos_prescription_app WITH CHECK (true);
CREATE POLICY prescription_items_update ON prescription_items FOR UPDATE TO ehos_prescription_app USING (deleted_at IS NULL);
CREATE POLICY prescription_items_delete ON prescription_items FOR DELETE TO ehos_prescription_app USING (false);

SELECT ehos_make_history('prescription_items');

-- ----------------------------------------------------------------------------
-- medication_administration
-- ----------------------------------------------------------------------------
CREATE TABLE medication_administration (
    id                  uuid primary key default gen_random_uuid(),
    patient_id          uuid not null,      -- cross-db ref to patient-service (no FK)
    prescription_id     uuid,               -- cross-db ref to prescriptions (no FK)
    prescription_item_id uuid references prescription_items(id),
    medication_id       uuid,               -- cross-db ref to pharmacy catalog (no FK)
    medication          text not null,
    dose                text not null,
    route               text,
    administered_by     uuid not null,      -- cross-db ref to hr-service (no FK)
    administered_at     timestamptz not null,
    documented_at       timestamptz not null default now(),
    batch_number        text,
    notes               text,
    reason_not_given    text,
    witness_id          uuid,               -- cross-db ref to hr-service (no FK)
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),
    created_by          uuid,
    updated_by          uuid,
    version             int not null default 1,
    status              text not null default 'GIVEN' check (status in ('GIVEN','REFUSED','MISSED','PARTIAL','HELD')),
    audit_reference     text,
    deleted_at          timestamptz,
    deleted_by          uuid,
    deletion_reason     text
);

CREATE INDEX idx_med_admin_patient ON medication_administration (patient_id, administered_at DESC);
CREATE INDEX idx_med_administration_prescription_item ON medication_administration (prescription_item_id);

ALTER TABLE medication_administration ENABLE ROW LEVEL SECURITY;
CREATE POLICY medication_administration_select ON medication_administration FOR SELECT TO ehos_prescription_app USING (deleted_at IS NULL);
CREATE POLICY medication_administration_insert ON medication_administration FOR INSERT TO ehos_prescription_app WITH CHECK (true);
CREATE POLICY medication_administration_update ON medication_administration FOR UPDATE TO ehos_prescription_app USING (deleted_at IS NULL);
CREATE POLICY medication_administration_delete ON medication_administration FOR DELETE TO ehos_prescription_app USING (false);

SELECT ehos_make_history('medication_administration');

-- ----------------------------------------------------------------------------
-- patient_allergies
-- ----------------------------------------------------------------------------
CREATE TABLE patient_allergies (
    id            uuid primary key default gen_random_uuid(),
    patient_id    uuid not null,            -- cross-db ref to patient-service (no FK)
    allergen      text not null,
    allergen_type text check (allergen_type in ('DRUG','FOOD','ENVIRONMENT','OTHER')),
    severity      text not null check (severity in ('MILD','MODERATE','SEVERE')),
    reaction      text,
    recorded_by   uuid not null,            -- cross-db ref to hr-service (no FK)
    recorded_at   timestamptz not null default now(),
    confirmed     boolean not null default false,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    created_by    uuid,
    updated_by    uuid,
    version       int not null default 1,
    status        text not null default 'ACTIVE',
    audit_reference text,
    deleted_at    timestamptz,
    deleted_by    uuid,
    deletion_reason text
);

CREATE UNIQUE INDEX uq_patient_allergies_patient_allergen_allergen_type
    ON patient_allergies (patient_id, allergen, allergen_type) WHERE deleted_at IS NULL;
CREATE INDEX idx_patient_allergies_patient ON patient_allergies (patient_id);

ALTER TABLE patient_allergies ENABLE ROW LEVEL SECURITY;
CREATE POLICY patient_allergies_select ON patient_allergies FOR SELECT TO ehos_prescription_app USING (deleted_at IS NULL);
CREATE POLICY patient_allergies_insert ON patient_allergies FOR INSERT TO ehos_prescription_app WITH CHECK (true);
CREATE POLICY patient_allergies_update ON patient_allergies FOR UPDATE TO ehos_prescription_app USING (deleted_at IS NULL);
CREATE POLICY patient_allergies_delete ON patient_allergies FOR DELETE TO ehos_prescription_app USING (false);

SELECT ehos_make_history('patient_allergies');

GRANT USAGE ON SCHEMA public TO ehos_prescription_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_prescription_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_prescription_app;

COMMIT;