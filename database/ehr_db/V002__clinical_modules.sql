-- ============================================================================
-- EHOS  ehr_db/V002__clinical_modules.sql
-- Service:      ehr-service
-- Description:  Clinical EHR modules: patient allergies, medications (clinical
--               medication orders), clinical orders (lab/imaging/procedure/etc.),
--               problem list, medical history and the clinical timeline.
--               Complements V001__init.sql (encounters, clinical_notes, diagnoses,
--               treatments, vital_signs, care_plans, referrals). Every table is
--               linked to patient_id (cross-db ref to patient-service, no FK)
--               per the database-per-service standard.
-- Design refs:  DATABASE_DESIGN.md sections 2.5, 2.6, 2.11, 6.1, 9, 10
-- NOTE: Shared objects applied before this file by apply.py.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- patient_allergies
-- ----------------------------------------------------------------------------
CREATE TABLE patient_allergies (
    id            uuid primary key default gen_random_uuid(),
    patient_id    uuid not null,              -- cross-db ref to patient-service (no FK)
    encounter_id  uuid references encounters(id),
    allergen      text not null,
    allergen_type text not null check (allergen_type in ('DRUG','FOOD','ENVIRONMENT','OTHER')),
    reaction      text,
    severity      text not null default 'UNKNOWN' check (severity in ('LOW','MEDIUM','HIGH','UNKNOWN')),
    onset_date    date,
    recorded_by   uuid,                       -- cross-db ref to hr-service (no FK)
    recorded_at   timestamptz not null default now(),
    resolved_by   uuid,
    resolved_at   timestamptz,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    created_by    uuid,
    updated_by    uuid,
    version       int not null default 1,
    status        text not null default 'ACTIVE' check (status in ('ACTIVE','RESOLVED')),
    audit_reference text,
    deleted_at    timestamptz,
    deleted_by    uuid,
    deletion_reason text
);

CREATE UNIQUE INDEX uq_patient_allergies_patient_allergen_type
    ON patient_allergies (patient_id, allergen, allergen_type) WHERE deleted_at IS NULL;
CREATE INDEX idx_patient_allergies_patient ON patient_allergies (patient_id);

ALTER TABLE patient_allergies ENABLE ROW LEVEL SECURITY;
CREATE POLICY patient_allergies_select ON patient_allergies FOR SELECT TO ehos_ehr_app USING (deleted_at IS NULL);
CREATE POLICY patient_allergies_insert ON patient_allergies FOR INSERT TO ehos_ehr_app WITH CHECK (true);
CREATE POLICY patient_allergies_update ON patient_allergies FOR UPDATE TO ehos_ehr_app USING (deleted_at IS NULL);
CREATE POLICY patient_allergies_delete ON patient_allergies FOR DELETE TO ehos_ehr_app USING (false);

SELECT ehos_make_history('patient_allergies');

-- ----------------------------------------------------------------------------
-- medications  (clinical medication orders captured in the chart)
-- ----------------------------------------------------------------------------
CREATE TABLE medications (
    id             uuid primary key default gen_random_uuid(),
    patient_id     uuid not null,             -- cross-db ref to patient-service (no FK)
    encounter_id   uuid references encounters(id),
    medication_id  uuid,                      -- cross-db ref to pharmacy catalog (no FK)
    medication_name text not null,
    strength       text,                      -- e.g. '500 mg'
    dose           numeric,
    dose_unit      text,                      -- mg, g, ml, drops...
    route          text not null default 'ORAL' check (route in ('ORAL','IV','IM','SC','TOPICAL','INHALED','RECTAL','SUBLINGUAL','OTIC','OPHTHALMIC','NASAL','OTHER')),
    frequency      text,                      -- e.g. 'TID', 'once daily'
    duration       text,
    prn            boolean not null default false,
    start_date     date,
    end_date       date,
    indication     text,
    instructions   text,
    prescriber_id  uuid,                      -- cross-db ref to hr-service (no FK)
    prescribed_at  timestamptz not null default now(),
    discontinued_by uuid,
    discontinued_at timestamptz,
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now(),
    created_by     uuid,
    updated_by     uuid,
    version        int not null default 1,
    status         text not null default 'ACTIVE' check (status in ('PLANNED','ACTIVE','COMPLETED','DISCONTINUED','HOLD','CANCELLED')),
    audit_reference text,
    deleted_at     timestamptz,
    deleted_by     uuid,
    deletion_reason text
);

CREATE INDEX idx_medications_patient ON medications (patient_id, prescribed_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_medications_encounter ON medications (encounter_id) WHERE encounter_id IS NOT NULL;

ALTER TABLE medications ENABLE ROW LEVEL SECURITY;
CREATE POLICY medications_select ON medications FOR SELECT TO ehos_ehr_app USING (deleted_at IS NULL);
CREATE POLICY medications_insert ON medications FOR INSERT TO ehos_ehr_app WITH CHECK (true);
CREATE POLICY medications_update ON medications FOR UPDATE TO ehos_ehr_app USING (deleted_at IS NULL);
CREATE POLICY medications_delete ON medications FOR DELETE TO ehos_ehr_app USING (false);

SELECT ehos_make_history('medications');

-- ----------------------------------------------------------------------------
-- clinical_orders  (lab / imaging / procedure / consult / nursing / diet / blood)
-- ----------------------------------------------------------------------------
CREATE TABLE clinical_orders (
    id               uuid primary key default gen_random_uuid(),
    patient_id       uuid not null,           -- cross-db ref to patient-service (no FK)
    encounter_id     uuid references encounters(id),
    order_type       text not null check (order_type in ('LAB','IMAGING','PROCEDURE','CONSULT','NURSING','DIET','BLOOD','OTHER')),
    description      text not null,
    priority         text not null default 'ROUTINE' check (priority in ('ROUTINE','URGENT','STAT','ASAP')),
    indications      text,
    requested_by     uuid,                    -- cross-db ref to hr-service (no FK)
    requested_at     timestamptz not null default now(),
    external_ref     uuid,                    -- cross-db ref to lab/radiology order (no FK)
    result_summary   text,
    completed_by     uuid,
    completed_at     timestamptz,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now(),
    created_by       uuid,
    updated_by       uuid,
    version          int not null default 1,
    status           text not null default 'REQUESTED' check (status in ('REQUESTED','IN_PROGRESS','COMPLETED','CANCELLED','HOLD')),
    audit_reference  text,
    deleted_at       timestamptz,
    deleted_by       uuid,
    deletion_reason  text
);

CREATE INDEX idx_clinical_orders_patient ON clinical_orders (patient_id, requested_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_clinical_orders_encounter ON clinical_orders (encounter_id) WHERE encounter_id IS NOT NULL;
CREATE INDEX idx_clinical_orders_type ON clinical_orders (order_type) WHERE deleted_at IS NULL;

ALTER TABLE clinical_orders ENABLE ROW LEVEL SECURITY;
CREATE POLICY clinical_orders_select ON clinical_orders FOR SELECT TO ehos_ehr_app USING (deleted_at IS NULL);
CREATE POLICY clinical_orders_insert ON clinical_orders FOR INSERT TO ehos_ehr_app WITH CHECK (true);
CREATE POLICY clinical_orders_update ON clinical_orders FOR UPDATE TO ehos_ehr_app USING (deleted_at IS NULL);
CREATE POLICY clinical_orders_delete ON clinical_orders FOR DELETE TO ehos_ehr_app USING (false);

SELECT ehos_make_history('clinical_orders');

-- ----------------------------------------------------------------------------
-- problem_list  (active/history of patient problems, coded where possible)
-- ----------------------------------------------------------------------------
CREATE TABLE problem_list (
    id             uuid primary key default gen_random_uuid(),
    patient_id     uuid not null,             -- cross-db ref to patient-service (no FK)
    problem        text not null,
    diagnosis_code text,
    code_system    text default 'ICD-10' check (code_system in ('ICD-10','ICD-11','SNOMED-CT')),
    onset_date     date,
    resolved_date  date,
    severity       text check (severity in ('LOW','MEDIUM','HIGH')),
    note           text,
    recorded_by    uuid,                      -- cross-db ref to hr-service (no FK)
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now(),
    created_by     uuid,
    updated_by     uuid,
    version        int not null default 1,
    status         text not null default 'ACTIVE' check (status in ('ACTIVE','INACTIVE','RESOLVED')),
    audit_reference text,
    deleted_at     timestamptz,
    deleted_by     uuid,
    deletion_reason text
);

CREATE INDEX idx_problem_list_patient ON problem_list (patient_id);
CREATE INDEX idx_problem_list_code ON problem_list (diagnosis_code) WHERE deleted_at IS NULL;

ALTER TABLE problem_list ENABLE ROW LEVEL SECURITY;
CREATE POLICY problem_list_select ON problem_list FOR SELECT TO ehos_ehr_app USING (deleted_at IS NULL);
CREATE POLICY problem_list_insert ON problem_list FOR INSERT TO ehos_ehr_app WITH CHECK (true);
CREATE POLICY problem_list_update ON problem_list FOR UPDATE TO ehos_ehr_app USING (deleted_at IS NULL);
CREATE POLICY problem_list_delete ON problem_list FOR DELETE TO ehos_ehr_app USING (false);

SELECT ehos_make_history('problem_list');

-- ----------------------------------------------------------------------------
-- medical_history  (past medical, surgical, family, social, obstetric, etc.)
-- ----------------------------------------------------------------------------
CREATE TABLE medical_history (
    id             uuid primary key default gen_random_uuid(),
    patient_id     uuid not null,             -- cross-db ref to patient-service (no FK)
    encounter_id   uuid references encounters(id),
    history_type   text not null check (history_type in ('PAST_MEDICAL','SURGICAL','FAMILY','SOCIAL','MEDICATION','ALLERGY','OBSTETRIC','GROWTH','IMMUNIZATION','OTHER')),
    description    text not null,
    occurred_date  date,
    resolved_date  date,
    facility       text,
    notes          text,
    recorded_by    uuid,                      -- cross-db ref to hr-service (no FK)
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now(),
    created_by     uuid,
    updated_by     uuid,
    version        int not null default 1,
    status         text not null default 'ACTIVE' check (status in ('ACTIVE','RESOLVED')),
    audit_reference text,
    deleted_at     timestamptz,
    deleted_by     uuid,
    deletion_reason text
);

CREATE INDEX idx_medical_history_patient ON medical_history (patient_id, history_type);
CREATE INDEX idx_medical_history_encounter ON medical_history (encounter_id) WHERE encounter_id IS NOT NULL;

ALTER TABLE medical_history ENABLE ROW LEVEL SECURITY;
CREATE POLICY medical_history_select ON medical_history FOR SELECT TO ehos_ehr_app USING (deleted_at IS NULL);
CREATE POLICY medical_history_insert ON medical_history FOR INSERT TO ehos_ehr_app WITH CHECK (true);
CREATE POLICY medical_history_update ON medical_history FOR UPDATE TO ehos_ehr_app USING (deleted_at IS NULL);
CREATE POLICY medical_history_delete ON medical_history FOR DELETE TO ehos_ehr_app USING (false);

SELECT ehos_make_history('medical_history');

-- ----------------------------------------------------------------------------
-- clinical_timeline  (source-tagged, per-patient event feed across all modules)
-- ----------------------------------------------------------------------------
CREATE TABLE clinical_timeline (
    id          uuid primary key default gen_random_uuid(),
    patient_id  uuid not null,                -- cross-db ref to patient-service (no FK)
    event_type  text not null check (event_type in (
        'ENCOUNTER_OPENED','ENCOUNTER_CLOSED',
        'NOTE_CREATED','NOTE_AMENDED','NOTE_SIGNED',
        'VITALS_RECORDED',
        'DIAGNOSIS_ADDED','DIAGNOSIS_RESOLVED',
        'MEDICATION_ORDERED','MEDICATION_DISCONTINUED',
        'ORDER_REQUESTED','ORDER_COMPLETED','ORDER_CANCELLED',
        'ALLERGY_ADDED','ALLERGY_RESOLVED',
        'PROBLEM_ADDED','PROBLEM_RESOLVED',
        'HISTORY_RECORDED',
        'TREATMENT_PLANNED',
        'REFERRAL_PLACED',
        'CARE_PLAN_CREATED'
    )),
    source      text not null default 'MANUAL' check (source in ('MANUAL','AI_DRAFT','VOICE','IMPORTED')),
    entity_type text,                          -- table/aggregate name, e.g. clinical_note
    entity_id   uuid,                          -- referenced row id
    occurred_at timestamptz not null default now(),
    actor_id    uuid,                          -- cross-db ref to hr/identity (no FK)
    details     jsonb,
    created_at  timestamptz not null default now()
);

CREATE INDEX idx_clinical_timeline_patient_time ON clinical_timeline (patient_id, occurred_at DESC);
CREATE INDEX idx_clinical_timeline_entity ON clinical_timeline (entity_type, entity_id);

-- ----------------------------------------------------------------------------
-- Grant the EHR app role read/write + history on the new PHI tables
-- ----------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_ehr_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_ehr_app;

COMMIT;