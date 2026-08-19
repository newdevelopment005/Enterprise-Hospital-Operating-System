-- ============================================================================
-- EHOS  ehr_db/V001__init.sql
-- Service:      ehr-service
-- Description:  Clinical record core: encounters, clinical notes (versions +
--               amendments), diagnoses, treatments, vital signs (RANGE
--               partitioned by recorded_at), care plans, care plan items,
--               referrals. Soft-delete + history for clinical data; RLS on PHI.
-- Design refs:  DATABASE_DESIGN.md sections 2.5, 2.6, 2.7, 2.8, 2.9, 2.11, 6.1, 9, 10
-- NOTE: Shared objects (pgcrypto, pg_trgm, fn_append_history(),
--       ehos_make_history(), outbox_events) are applied BEFORE this file by
--       apply.py and are NOT re-created here.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- encounters
-- ----------------------------------------------------------------------------
CREATE TABLE encounters (
    id               uuid primary key default gen_random_uuid(),
    patient_id       uuid not null,          -- cross-db ref to patient-service (no FK)
    patient_snapshot jsonb,
    encounter_type   text not null check (encounter_type in ('OUTPATIENT','INPATIENT','ED','SURGERY','TELEHEALTH','HOME')),
    department_id    uuid,                   -- cross-db ref to hr-service (no FK)
    provider_id      uuid,                   -- cross-db ref to hr-service (no FK)
    start_time       timestamptz not null,
    end_time         timestamptz,
    admission_id     uuid,                   -- cross-db ref to bed-service (no FK)
    visit_number     text,
    reason           text,
    billing_lock     boolean not null default false,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now(),
    created_by       uuid,
    updated_by       uuid,
    version          int not null default 1,
    status           text not null default 'OPEN' check (status in ('PLANNED','OPEN','IN_PROGRESS','CLOSED','CANCELLED')),
    audit_reference  text,
    deleted_at       timestamptz,
    deleted_by       uuid,
    deletion_reason  text
);

CREATE INDEX idx_encounters_patient ON encounters (patient_id, start_time DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_encounters_provider_time ON encounters (provider_id, start_time) WHERE deleted_at IS NULL;

SELECT ehos_make_history('encounters');

-- ----------------------------------------------------------------------------
-- clinical_notes
-- ----------------------------------------------------------------------------
CREATE TABLE clinical_notes (
    id               uuid primary key default gen_random_uuid(),
    encounter_id     uuid references encounters(id),
    patient_id       uuid not null,          -- cross-db ref to patient-service (no FK)
    author_id        uuid not null,          -- cross-db ref to hr/identity (no FK)
    author_role      text,
    note_type        text not null check (note_type in ('SOAP','PROGRESS','ADMISSION','DISCHARGE','CONSULT','NURSING','OPNOTE','AI_DRAFT')),
    content          text not null,
    content_struct   jsonb,
    approval_status  text not null default 'DRAFT' check (approval_status in ('DRAFT','PENDING_REVIEW','APPROVED','SIGNED','REJECTED','RETRACTED')),
    approved_by      uuid,
    approved_at      timestamptz,
    signed_by        uuid,
    signed_at        timestamptz,
    source           text check (source in ('MANUAL','AI_DRAFT','VOICE','IMPORTED')),
    ai_draft_ref     uuid,                   -- optional link to ai request (no FK)
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now(),
    created_by       uuid,
    updated_by       uuid,
    version          int not null default 1,
    status           text not null default 'ACTIVE',
    audit_reference  text,
    deleted_at       timestamptz,
    deleted_by       uuid,
    deletion_reason  text
);

CREATE INDEX idx_clinical_notes_encounter ON clinical_notes (encounter_id);
CREATE INDEX idx_clinical_notes_patient_note ON clinical_notes (patient_id, note_type) WHERE deleted_at IS NULL;

ALTER TABLE clinical_notes ENABLE ROW LEVEL SECURITY;
CREATE POLICY clinical_notes_select ON clinical_notes FOR SELECT TO ehos_ehr_app USING (deleted_at IS NULL);
CREATE POLICY clinical_notes_insert ON clinical_notes FOR INSERT TO ehos_ehr_app WITH CHECK (true);
CREATE POLICY clinical_notes_update ON clinical_notes FOR UPDATE TO ehos_ehr_app USING (deleted_at IS NULL);
CREATE POLICY clinical_notes_delete ON clinical_notes FOR DELETE TO ehos_ehr_app USING (false);

SELECT ehos_make_history('clinical_notes');

-- ----------------------------------------------------------------------------
-- clinical_note_versions
-- NOTE: application-level revision artifact (design 6.1); already the version
--       table, carries no common-block columns, so no ehos_make_history().
-- ----------------------------------------------------------------------------
CREATE TABLE clinical_note_versions (
    id             uuid primary key default gen_random_uuid(),
    note_id        uuid not null references clinical_notes(id),
    version_no     int not null,
    content        text not null,
    content_struct jsonb,
    author_id      uuid,
    change_reason  text,
    created_at     timestamptz not null default now(),
    constraint uq_clinical_note_versions_note_version unique (note_id, version_no)
);

CREATE INDEX idx_clinical_note_versions_note ON clinical_note_versions (note_id);

-- ----------------------------------------------------------------------------
-- clinical_note_amendments
-- NOTE: append-only addenda (design 6.1); no common-block version columns, so
--       no ehos_make_history().
-- ----------------------------------------------------------------------------
CREATE TABLE clinical_note_amendments (
    id              uuid primary key default gen_random_uuid(),
    note_id         uuid not null references clinical_notes(id),
    author_id       uuid not null,
    amendment       text not null,
    added_at        timestamptz not null default now(),
    audit_reference text
);

CREATE INDEX idx_clinical_note_amendments_note ON clinical_note_amendments (note_id);

-- ----------------------------------------------------------------------------
-- diagnoses
-- ----------------------------------------------------------------------------
CREATE TABLE diagnoses (
    id                  uuid primary key default gen_random_uuid(),
    encounter_id        uuid not null references encounters(id),
    patient_id          uuid not null,       -- cross-db ref to patient-service (no FK)
    diagnosis_code      text not null,
    code_system         text not null default 'ICD-10' check (code_system in ('ICD-10','ICD-11','SNOMED-CT')),
    description         text not null,
    type                text not null default 'WORKING' check (type in ('WORKING','PROVISIONAL','FINAL','ADMISSION','DISCHARGE','DEATH')),
    onset_date          date,
    diagnosed_by        uuid not null,       -- cross-db ref to hr-service (no FK)
    diagnosed_at        timestamptz not null default now(),
    resolved_at         timestamptz,
    resolved_by         uuid,
    present_on_admission boolean,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),
    created_by          uuid,
    updated_by          uuid,
    version             int not null default 1,
    status              text not null default 'ACTIVE' check (status in ('ACTIVE','RESOLVED','REJECTED')),
    audit_reference     text,
    deleted_at          timestamptz,
    deleted_by          uuid,
    deletion_reason     text
);

CREATE INDEX idx_diagnoses_patient ON diagnoses (patient_id);
CREATE INDEX idx_diagnoses_code ON diagnoses (diagnosis_code) WHERE deleted_at IS NULL;
CREATE INDEX idx_diagnoses_encounter ON diagnoses (encounter_id);

ALTER TABLE diagnoses ENABLE ROW LEVEL SECURITY;
CREATE POLICY diagnoses_select ON diagnoses FOR SELECT TO ehos_ehr_app USING (deleted_at IS NULL);
CREATE POLICY diagnoses_insert ON diagnoses FOR INSERT TO ehos_ehr_app WITH CHECK (true);
CREATE POLICY diagnoses_update ON diagnoses FOR UPDATE TO ehos_ehr_app USING (deleted_at IS NULL);
CREATE POLICY diagnoses_delete ON diagnoses FOR DELETE TO ehos_ehr_app USING (false);

SELECT ehos_make_history('diagnoses');

-- ----------------------------------------------------------------------------
-- treatments
-- ----------------------------------------------------------------------------
CREATE TABLE treatments (
    id             uuid primary key default gen_random_uuid(),
    patient_id     uuid not null,           -- cross-db ref to patient-service (no FK)
    encounter_id   uuid references encounters(id),
    treatment_type text not null check (treatment_type in ('PROCEDURE','MEDICATION','THERAPY','SURGERY','CARE_PLAN','OTHER')),
    description    text not null,
    provider_id    uuid,                    -- cross-db ref to hr-service (no FK)
    scheduled_at   timestamptz,
    performed_at   timestamptz,
    outcome        text,
    complications  text,
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now(),
    created_by     uuid,
    updated_by     uuid,
    version        int not null default 1,
    status         text not null default 'PLANNED' check (status in ('PLANNED','IN_PROGRESS','COMPLETED','CANCELLED','STOPPED')),
    audit_reference text,
    deleted_at     timestamptz,
    deleted_by     uuid,
    deletion_reason text
);

CREATE INDEX idx_treatments_patient ON treatments (patient_id);
CREATE INDEX idx_treatments_encounter ON treatments (encounter_id);

ALTER TABLE treatments ENABLE ROW LEVEL SECURITY;
CREATE POLICY treatments_select ON treatments FOR SELECT TO ehos_ehr_app USING (deleted_at IS NULL);
CREATE POLICY treatments_insert ON treatments FOR INSERT TO ehos_ehr_app WITH CHECK (true);
CREATE POLICY treatments_update ON treatments FOR UPDATE TO ehos_ehr_app USING (deleted_at IS NULL);
CREATE POLICY treatments_delete ON treatments FOR DELETE TO ehos_ehr_app USING (false);

SELECT ehos_make_history('treatments');

-- ----------------------------------------------------------------------------
-- vital_signs (partition parent)
-- NOTE: RANGE-partitioned by recorded_at (design 2.9); partitioned parent, so
--       no ehos_make_history() on vital_signs (indexes carry to partitions).
-- ----------------------------------------------------------------------------
CREATE TABLE vital_signs (
    id            uuid not null default gen_random_uuid(),
    patient_id    uuid not null,             -- cross-db ref to patient-service (no FK)
    encounter_id  uuid references encounters(id),
    recorded_at   timestamptz not null default now(),
    -- PG16 requires PK on partitioned tables to include the partition key:
    PRIMARY KEY (id, recorded_at),
    recorded_by   uuid,                      -- cross-db ref to hr-service (no FK)
    vital_type    text not null check (vital_type in ('BP','HR','RR','TEMP','SPO2','WEIGHT','HEIGHT','BMI','GLUCOSE','PAIN','GCS')),
    value_numeric numeric,
    value_text    text,
    unit          text,
    notion        jsonb,
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
) PARTITION BY RANGE (recorded_at);

CREATE TABLE vital_signs_default PARTITION OF vital_signs FOR VALUES FROM (MINVALUE) TO (MAXVALUE);

CREATE INDEX idx_vital_signs_patient_time ON vital_signs (patient_id, recorded_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_vital_signs_encounter ON vital_signs (encounter_id);

-- ----------------------------------------------------------------------------
-- care_plans
-- ----------------------------------------------------------------------------
CREATE TABLE care_plans (
    id           uuid primary key default gen_random_uuid(),
    patient_id   uuid not null,              -- cross-db ref to patient-service (no FK)
    encounter_id uuid references encounters(id),
    title        text not null,
    description  text,
    goal         text,
    start_date   date,
    end_date     date,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),
    created_by   uuid,
    updated_by   uuid,
    version      int not null default 1,
    status       text not null default 'ACTIVE' check (status in ('ACTIVE','COMPLETED','PAUSED','CANCELLED')),
    audit_reference text,
    deleted_at   timestamptz,
    deleted_by   uuid,
    deletion_reason text
);

CREATE INDEX idx_care_plans_patient ON care_plans (patient_id);
CREATE INDEX idx_care_plans_encounter ON care_plans (encounter_id);

SELECT ehos_make_history('care_plans');

-- ----------------------------------------------------------------------------
-- care_plan_items
-- ----------------------------------------------------------------------------
CREATE TABLE care_plan_items (
    id           uuid primary key default gen_random_uuid(),
    care_plan_id uuid not null references care_plans(id),
    item_type    text not null check (item_type in ('MEDICATION','PROCEDURE','REFERRAL','FOLLOWUP','EDUCATION','OTHER')),
    description  text not null,
    due_date     date,
    completed    boolean default false,
    completed_by uuid,
    completed_at timestamptz,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),
    created_by   uuid,
    updated_by   uuid,
    version      int not null default 1,
    status       text not null default 'ACTIVE',
    audit_reference text,
    deleted_at   timestamptz,
    deleted_by   uuid,
    deletion_reason text
);

CREATE INDEX idx_care_plan_items_plan ON care_plan_items (care_plan_id);

SELECT ehos_make_history('care_plan_items');

-- ----------------------------------------------------------------------------
-- referrals
-- ----------------------------------------------------------------------------
CREATE TABLE referrals (
    id                 uuid primary key default gen_random_uuid(),
    patient_id         uuid not null,        -- cross-db ref to patient-service (no FK)
    encounter_id       uuid references encounters(id),
    referred_from_dept uuid,                 -- cross-db ref to hr-service (no FK)
    referred_to_dept   uuid,                 -- cross-db ref to hr-service (no FK)
    referred_by        uuid,                 -- cross-db ref to hr-service (no FK)
    referral_type      text not null check (referral_type in ('INTERNAL','EXTERNAL','SPECIALIST','TRANSFER')),
    reason             text,
    accepted_by        uuid,
    accepted_at        timestamptz,
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now(),
    created_by         uuid,
    updated_by         uuid,
    version            int not null default 1,
    status             text not null default 'ACTIVE' check (status in ('ACTIVE','ACCEPTED','DECLINED','COMPLETED','CANCELLED')),
    audit_reference    text,
    deleted_at         timestamptz,
    deleted_by         uuid,
    deletion_reason    text
);

CREATE INDEX idx_referrals_patient ON referrals (patient_id);
CREATE INDEX idx_referrals_encounter ON referrals (encounter_id);

SELECT ehos_make_history('referrals');

GRANT USAGE ON SCHEMA public TO ehos_ehr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_ehr_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_ehr_app;

COMMIT;