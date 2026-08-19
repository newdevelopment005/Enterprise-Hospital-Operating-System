-- ============================================================================
-- EHOS  laboratory_db  V001__init.sql
-- laboratory-service: lab test catalog, orders, samples, results & verification.
-- Design: DATABASE_DESIGN.md sections 6.5, 2.5-2.7, 10; role 00_db_roles.sql.
-- Shared objects (pgcrypto, pg_trgm, fn_append_history(), ehos_make_history(),
-- outbox_events) are applied FIRST by apply.py; not included here.
-- Postgres 16+, lowercase snake_case.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- lab_tests — test catalog
-- ----------------------------------------------------------------------------
CREATE TABLE lab_tests (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code           TEXT NOT NULL,
    name           TEXT NOT NULL,
    category       TEXT NOT NULL,
    unit           TEXT,
    reference_low  NUMERIC,
    reference_high NUMERIC,
    specimen_type  TEXT,
    turnaround_min INT,
    is_active      BOOLEAN NOT NULL DEFAULT true,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by     UUID,
    updated_by     UUID,
    version        INT NOT NULL DEFAULT 1,
    status         TEXT NOT NULL,
    audit_reference TEXT,
    deleted_at     TIMESTAMPTZ,
    deleted_by     UUID,
    deletion_reason TEXT
);

CREATE UNIQUE INDEX uq_lab_tests_code ON lab_tests (code) WHERE deleted_at IS NULL;

-- ----------------------------------------------------------------------------
-- lab_orders — order header
-- ----------------------------------------------------------------------------
CREATE TABLE lab_orders (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id       UUID NOT NULL,
    patient_snapshot JSONB,
    encounter_id     UUID,
    ordering_doctor  UUID NOT NULL,
    priority         TEXT NOT NULL DEFAULT 'ROUTINE' CHECK (priority IN ('ROUTINE','URGENT','STAT')),
    ordered_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    clinical_notes   TEXT,
    status           TEXT NOT NULL DEFAULT 'ORDERED' CHECK (status IN ('ORDERED','COLLECTED','IN_PROGRESS','RESULTED','VERIFIED','CANCELLED')),
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

CREATE INDEX idx_lab_orders_patient ON lab_orders (patient_id, ordered_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_lab_orders_doctor ON lab_orders (ordering_doctor);
CREATE INDEX idx_lab_orders_encounter ON lab_orders (encounter_id) WHERE encounter_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- lab_order_items
-- ----------------------------------------------------------------------------
CREATE TABLE lab_order_items (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lab_order_id  UUID NOT NULL REFERENCES lab_orders(id),
    test_id       UUID REFERENCES lab_tests(id),
    test_name     TEXT NOT NULL,
    specimen_type TEXT,
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

CREATE INDEX idx_lab_order_items_order ON lab_order_items (lab_order_id);
CREATE INDEX idx_lab_order_items_test ON lab_order_items (test_id) WHERE test_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- samples — collection & tracking
-- ----------------------------------------------------------------------------
CREATE TABLE samples (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lab_order_id     UUID NOT NULL REFERENCES lab_orders(id),
    patient_id       UUID NOT NULL,
    barcode          TEXT NOT NULL,
    sample_type      TEXT NOT NULL,
    collection_time  TIMESTAMPTZ,
    collected_by     UUID,
    received_at      TIMESTAMPTZ,
    received_by      UUID,
    status           TEXT NOT NULL DEFAULT 'REQUESTED' CHECK (status IN ('REQUESTED','COLLECTED','IN_TRANSIT','RECEIVED','ANALYZED','REJECTED','DISCARDED')),
    rejection_reason TEXT,
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

CREATE UNIQUE INDEX uq_samples_barcode ON samples (barcode) WHERE deleted_at IS NULL;
CREATE INDEX idx_samples_order ON samples (lab_order_id);
CREATE INDEX idx_samples_patient ON samples (patient_id);

-- ----------------------------------------------------------------------------
-- lab_results — verified clinical data (RLS-protected)
-- ----------------------------------------------------------------------------
CREATE TABLE lab_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_item_id   UUID NOT NULL REFERENCES lab_order_items(id),
    sample_id       UUID REFERENCES samples(id),
    patient_id      UUID NOT NULL,
    test_id         UUID REFERENCES lab_tests(id),
    test_name       TEXT NOT NULL,
    result_numeric  NUMERIC,
    result_text     TEXT,
    unit            TEXT,
    reference_range TEXT,
    flag            TEXT CHECK (flag IN ('NORMAL','HIGH','LOW','CRITICAL','ABNORMAL')),
    performed_by    UUID,
    performed_at    TIMESTAMPTZ,
    verified_by     UUID,
    verified_at     TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'PRELIMINARY' CHECK (status IN ('PRELIMINARY','VERIFIED','AMENDED','CANCELLED')),
    instrumentation TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID,
    updated_by      UUID,
    version         INT NOT NULL DEFAULT 1,
    audit_reference TEXT,
    deleted_at      TIMESTAMPTZ,
    deleted_by      UUID,
    deletion_reason TEXT
);

CREATE INDEX idx_lab_results_patient ON lab_results (patient_id, performed_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_lab_results_order ON lab_results (order_item_id);
CREATE INDEX idx_lab_results_sample ON lab_results (sample_id) WHERE sample_id IS NOT NULL;
CREATE INDEX idx_lab_results_test ON lab_results (test_id) WHERE test_id IS NOT NULL;

-- RLS per design section 2.11 / 10
ALTER TABLE lab_results ENABLE ROW LEVEL SECURITY;

CREATE POLICY lab_results_select ON lab_results
    FOR SELECT TO ehos_laboratory_app
    USING (deleted_at IS NULL);

CREATE POLICY lab_results_insert ON lab_results
    FOR INSERT TO ehos_laboratory_app
    WITH CHECK (deleted_at IS NULL);

CREATE POLICY lab_results_update ON lab_results
    FOR UPDATE TO ehos_laboratory_app
    USING (deleted_at IS NULL)
    WITH CHECK (deleted_at IS NULL);

CREATE POLICY lab_results_delete ON lab_results
    FOR DELETE TO ehos_laboratory_app
    USING (deleted_at IS NULL);

-- ----------------------------------------------------------------------------
-- history tables
-- ----------------------------------------------------------------------------
SELECT ehos_make_history('lab_tests');
SELECT ehos_make_history('lab_orders');
SELECT ehos_make_history('lab_order_items');
SELECT ehos_make_history('samples');
SELECT ehos_make_history('lab_results');

-- ----------------------------------------------------------------------------
-- grants to application role
-- ----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO ehos_laboratory_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_laboratory_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_laboratory_app;

COMMIT;