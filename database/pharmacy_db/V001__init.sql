-- ============================================================================
-- EHOS  pharmacy_db/V001__init.sql
-- Service:      pharmacy-service
-- Description:  Medication catalog (trigram search), stock levels with batch
--               expiry tracking, dispensing records, and the controlled-drug
--               log (2-person witness) for drugs of addiction.
-- Design refs:  DATABASE_DESIGN.md sections 2.5, 2.6, 2.7, 2.8, 6.4, 9, 10
-- NOTE: Shared objects (pgcrypto, pg_trgm, fn_append_history(),
--       ehos_make_history(), outbox_events) are applied BEFORE this file by
--       apply.py and are NOT re-created here.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- medications
-- ----------------------------------------------------------------------------
CREATE TABLE medications (
    id           uuid primary key default gen_random_uuid(),
    code         text not null,
    name         text not null,
    generic_name text,
    manufacturer text,
    strength     text,
    form         text,
    controlled   boolean not null default false,
    atc_code     text,
    attributes   jsonb,
    is_active    boolean not null default true,
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

CREATE UNIQUE INDEX uq_medications_code ON medications (code) WHERE deleted_at IS NULL;
CREATE INDEX idx_medications_name_trgm ON medications USING gin (name gin_trgm_ops);

SELECT ehos_make_history('medications');

-- ----------------------------------------------------------------------------
-- stock_levels
-- ----------------------------------------------------------------------------
CREATE TABLE stock_levels (
    id           uuid primary key default gen_random_uuid(),
    medication_id uuid not null references medications(id),
    location     text not null,
    quantity     numeric not null default 0 check (quantity >= 0),
    reserved     numeric not null default 0,
    batch_number text,
    expiry_date  date,
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

CREATE UNIQUE INDEX uq_stock_levels_medication_location_batch
    ON stock_levels (medication_id, location, batch_number) WHERE deleted_at IS NULL;
CREATE INDEX idx_stock_levels_expiry ON stock_levels (expiry_date) WHERE deleted_at IS NULL AND quantity > 0;
CREATE INDEX idx_stock_levels_medication ON stock_levels (medication_id);

SELECT ehos_make_history('stock_levels');

-- ----------------------------------------------------------------------------
-- dispensing_records
-- ----------------------------------------------------------------------------
CREATE TABLE dispensing_records (
    id                  uuid primary key default gen_random_uuid(),
    patient_id          uuid not null,      -- cross-db ref to patient-service (no FK)
    prescription_id     uuid,               -- cross-db ref to prescription-service (no FK)
    prescription_item_id uuid,              -- cross-db ref to prescription-service (no FK)
    medication_id       uuid not null references medications(id),
    quantity            numeric not null,
    dispensed_by        uuid not null,      -- cross-db ref to hr-service (no FK)
    dispensed_at        timestamptz not null default now(),
    batch_number        text,
    price               numeric(12,2),
    charge_id           uuid,               -- cross-db ref to billing-service (no FK)
    notes               text,
    returned_at         timestamptz,
    returned_reason     text,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),
    created_by          uuid,
    updated_by          uuid,
    version             int not null default 1,
    status              text not null default 'DISPENSED' check (status in ('PREPARED','DISPENSED','PICKED_UP','RETURNED','EXPIRED','SPOILED')),
    audit_reference     text,
    deleted_at          timestamptz,
    deleted_by          uuid,
    deletion_reason     text
);

CREATE INDEX idx_dispensing_records_patient ON dispensing_records (patient_id, dispensed_at DESC);
CREATE INDEX idx_dispensing_records_medication ON dispensing_records (medication_id);

SELECT ehos_make_history('dispensing_records');

-- ----------------------------------------------------------------------------
-- controlled_drug_log
-- ----------------------------------------------------------------------------
CREATE TABLE controlled_drug_log (
    id            uuid primary key default gen_random_uuid(),
    medication_id uuid not null references medications(id),
    batch_number  text not null,
    action        text not null check (action in ('RECEIVED','ISSUED','RETURNED','DISCARDED','COUNT')),
    quantity      numeric not null,
    balance_after numeric not null,
    actor_id      uuid not null,            -- cross-db ref to hr-service (no FK)
    witness_id    uuid not null,            -- cross-db ref to hr-service (no FK)
    occurred_at   timestamptz not null default now(),
    balance_check boolean not null default false,
    notes         text,
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

CREATE INDEX idx_controlled_drug_log_med ON controlled_drug_log (medication_id, occurred_at DESC);

SELECT ehos_make_history('controlled_drug_log');

GRANT USAGE ON SCHEMA public TO ehos_pharmacy_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_pharmacy_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_pharmacy_app;

COMMIT;