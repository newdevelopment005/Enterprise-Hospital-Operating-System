-- ============================================================================
-- EHOS  billing_db / V001__init.sql
-- Service: billing-service
-- Description: Baseline schema for the billing database: charges, invoices,
--   invoice_items, payments, receipts and adjustments. Financial records are
--   NEVER hard-deleted; corrections are recorded as adjustment entries, never
--   in-place edits. RLS is enabled on payments.
-- Design: DATABASE_DESIGN.md sections 2, 7.1, 2.11, 9, 10.
-- Requires: shared 01_extensions.sql (pgcrypto, pg_trgm), 02_history_trigger.sql
--   (fn_append_history(), ehos_make_history()), 03_outbox.sql (outbox_events)
--   applied first by apply.py. No \i includes in this file.
-- Postgres 16+, lowercase snake_case, app role: ehos_billing_app.
-- ============================================================================

BEGIN;

CREATE TABLE charges (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id      UUID NOT NULL,
    encounter_id    UUID,
    service_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    item_type       TEXT NOT NULL,
    item_code       TEXT,
    description     TEXT NOT NULL,
    quantity        NUMERIC(12,2) NOT NULL DEFAULT 1,
    unit_price      NUMERIC(12,2) NOT NULL,
    discount        NUMERIC(12,2) NOT NULL DEFAULT 0,
    source_service  TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING','BILLED','ADJUSTED','VOIDED','REVERSED')),
    billing_ref     UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID,
    updated_by      UUID,
    version         INT NOT NULL DEFAULT 1,
    audit_reference TEXT,
    deleted_at      TIMESTAMPTZ,
    deleted_by      UUID,
    deletion_reason TEXT,
    CHECK (quantity >= 0),
    CHECK (unit_price >= 0)
);

CREATE INDEX idx_charges_patient ON charges (patient_id, service_date) WHERE deleted_at IS NULL;
CREATE INDEX idx_charges_status ON charges (status);

SELECT ehos_make_history('charges');

CREATE TABLE invoices (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_number   TEXT NOT NULL,
    patient_id       UUID NOT NULL,
    total_amount     NUMERIC(12,2) NOT NULL,
    insurance_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    patient_amount   NUMERIC(12,2) NOT NULL DEFAULT 0,
    paid_amount      NUMERIC(12,2) NOT NULL DEFAULT 0,
    discount_amount  NUMERIC(12,2) NOT NULL DEFAULT 0,
    tax_amount       NUMERIC(12,2) NOT NULL DEFAULT 0,
    currency         TEXT NOT NULL DEFAULT 'EGP',
    issued_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    due_date         DATE,
    status           TEXT NOT NULL DEFAULT 'UNPAID'
                     CHECK (status IN ('UNPAID','PARTIALLY_PAID','PAID','OVERDUE','VOID','CREDIT_NOTE')),
    void_reason      TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    version          INT NOT NULL DEFAULT 1,
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason  TEXT,
    CHECK (total_amount >= 0)
);

CREATE UNIQUE INDEX uq_invoices_invoice_number ON invoices (invoice_number) WHERE deleted_at IS NULL;
CREATE INDEX idx_invoices_patient ON invoices (patient_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_invoices_status_date ON invoices (status, issued_date);

SELECT ehos_make_history('invoices');

CREATE TABLE invoice_items (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id   UUID NOT NULL REFERENCES invoices(id),
    charge_id    UUID REFERENCES charges(id),
    description  TEXT NOT NULL,
    quantity     NUMERIC(12,2) NOT NULL,
    unit_price   NUMERIC(12,2) NOT NULL,
    amount       NUMERIC(12,2) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by   UUID,
    updated_by   UUID,
    version      INT NOT NULL DEFAULT 1,
    status       TEXT NOT NULL,
    audit_reference TEXT,
    deleted_at   TIMESTAMPTZ,
    deleted_by   UUID,
    deletion_reason TEXT
);

CREATE INDEX idx_invoice_items_invoice ON invoice_items (invoice_id);
CREATE INDEX idx_invoice_items_charge ON invoice_items (charge_id);

SELECT ehos_make_history('invoice_items');

CREATE TABLE payments (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id     UUID REFERENCES invoices(id),
    patient_id     UUID NOT NULL,
    amount         NUMERIC(12,2) NOT NULL,
    payment_method TEXT NOT NULL CHECK (payment_method IN ('CASH','CARD','WALLET','BANK','INSURANCE','ONLINE')),
    provider_ref   TEXT,
    payment_date   TIMESTAMPTZ NOT NULL DEFAULT now(),
    received_by    UUID,
    status         TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','APPROVED','FAILED','REFUNDED','VOIDED')),
    refund_of      UUID,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by     UUID,
    updated_by     UUID,
    version        INT NOT NULL DEFAULT 1,
    audit_reference TEXT,
    deleted_at     TIMESTAMPTZ,
    deleted_by     UUID,
    deletion_reason TEXT,
    CHECK (amount > 0)
);

CREATE INDEX idx_payments_invoice ON payments (invoice_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_payments_patient_date ON payments (patient_id, payment_date) WHERE deleted_at IS NULL;

SELECT ehos_make_history('payments');

CREATE TABLE receipts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id     UUID NOT NULL REFERENCES payments(id),
    receipt_number TEXT NOT NULL,
    issued_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    issued_by      UUID,
    receipt_ref    TEXT,
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

CREATE UNIQUE INDEX uq_receipts_receipt_number ON receipts (receipt_number) WHERE deleted_at IS NULL;
CREATE INDEX idx_receipts_payment ON receipts (payment_id);

SELECT ehos_make_history('receipts');

CREATE TABLE adjustments (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id              UUID REFERENCES invoices(id),
    patient_id              UUID NOT NULL,
    adjustment_type         TEXT NOT NULL CHECK (adjustment_type IN ('DISCOUNT','REBATE','VOID','CORRECTION','WRITE_OFF')),
    amount                  NUMERIC(12,2) NOT NULL,
    reason                  TEXT NOT NULL,
    applied_by              UUID,
    applied_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    original_invoice_item_id UUID,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by              UUID,
    updated_by              UUID,
    version                 INT NOT NULL DEFAULT 1,
    status                  TEXT NOT NULL,
    audit_reference         TEXT,
    deleted_at              TIMESTAMPTZ,
    deleted_by              UUID,
    deletion_reason         TEXT,
    CHECK (amount >= 0)
);

CREATE INDEX idx_adjustments_invoice ON adjustments (invoice_id);

SELECT ehos_make_history('adjustments');

ALTER TABLE payments ENABLE ROW LEVEL SECURITY;

CREATE POLICY payments_select ON payments
    FOR SELECT TO ehos_billing_app USING (deleted_at IS NULL);
CREATE POLICY payments_insert ON payments
    FOR INSERT TO ehos_billing_app WITH CHECK (true);
CREATE POLICY payments_update ON payments
    FOR UPDATE TO ehos_billing_app USING (deleted_at IS NULL) WITH CHECK (deleted_at IS NULL);
CREATE POLICY payments_delete ON payments
    FOR DELETE TO ehos_billing_app USING (false);

GRANT USAGE ON SCHEMA public TO ehos_billing_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_billing_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_billing_app;

COMMIT;