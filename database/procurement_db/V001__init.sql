-- ============================================================================
-- EHOS  procurement_db / V001__init.sql
-- Service: procurement-service
-- Description: Baseline schema for the procurement database: suppliers,
--   purchase requisitions, purchase orders, purchase order items and goods
--   receipts.
-- Design: DATABASE_DESIGN.md sections 2, 7.5, 9, 10.
-- Requires: shared 01_extensions.sql (pgcrypto, pg_trgm), 02_history_trigger.sql
--   (fn_append_history(), ehos_make_history()), 03_outbox.sql (outbox_events)
--   applied first by apply.py. No \i includes in this file.
-- Postgres 16+, lowercase snake_case, app role: ehos_procurement_app.
-- ============================================================================

BEGIN;

CREATE TABLE suppliers (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code          TEXT NOT NULL,
    name          TEXT NOT NULL,
    tax_id        TEXT,
    contact       JSONB,
    payment_terms TEXT,
    is_active     BOOLEAN NOT NULL DEFAULT true,
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

CREATE UNIQUE INDEX uq_suppliers_code ON suppliers (code) WHERE deleted_at IS NULL;

SELECT ehos_make_history('suppliers');

CREATE TABLE purchase_requisitions (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requester_id  UUID NOT NULL,
    department_id UUID,
    description   TEXT,
    status        TEXT NOT NULL DEFAULT 'SUBMITTED'
                  CHECK (status IN ('SUBMITTED','APPROVED','REJECTED','ORDERED','CANCELLED')),
    approved_by   UUID,
    approved_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by    UUID,
    updated_by    UUID,
    version       INT NOT NULL DEFAULT 1,
    audit_reference TEXT,
    deleted_at    TIMESTAMPTZ,
    deleted_by    UUID,
    deletion_reason TEXT
);

CREATE INDEX idx_purchase_requisitions_status ON purchase_requisitions (status);

SELECT ehos_make_history('purchase_requisitions');

CREATE TABLE purchase_orders (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    po_number     TEXT NOT NULL,
    supplier_id   UUID NOT NULL REFERENCES suppliers(id),
    requisition_id UUID REFERENCES purchase_requisitions(id),
    order_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    expected_date DATE,
    total_amount  NUMERIC(12,2) NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'DRAFT'
                  CHECK (status IN ('DRAFT','SUBMITTED','APPROVED','PLACED','PARTIALLY_RECEIVED','RECEIVED','CANCELLED')),
    approved_by   UUID,
    approved_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by    UUID,
    updated_by    UUID,
    version       INT NOT NULL DEFAULT 1,
    audit_reference TEXT,
    deleted_at    TIMESTAMPTZ,
    deleted_by    UUID,
    deletion_reason TEXT,
    CHECK (total_amount >= 0)
);

CREATE UNIQUE INDEX uq_purchase_orders_po_number ON purchase_orders (po_number) WHERE deleted_at IS NULL;
CREATE INDEX idx_purchase_orders_supplier ON purchase_orders (supplier_id);
CREATE INDEX idx_purchase_orders_requisition ON purchase_orders (requisition_id);
CREATE INDEX idx_purchase_orders_status ON purchase_orders (status);

SELECT ehos_make_history('purchase_orders');

CREATE TABLE purchase_order_items (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purchase_order_id UUID NOT NULL REFERENCES purchase_orders(id),
    item_id           UUID,
    item_name         TEXT NOT NULL,
    quantity          NUMERIC NOT NULL,
    unit_price        NUMERIC(12,2) NOT NULL,
    received_qty      NUMERIC NOT NULL DEFAULT 0,
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

CREATE INDEX idx_po_items_order ON purchase_order_items (purchase_order_id);

SELECT ehos_make_history('purchase_order_items');

CREATE TABLE goods_receipts (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purchase_order_id UUID NOT NULL REFERENCES purchase_orders(id),
    received_date     DATE NOT NULL DEFAULT CURRENT_DATE,
    received_by       UUID NOT NULL,
    status            TEXT NOT NULL DEFAULT 'RECEIVED' CHECK (status IN ('RECEIVED','PARTIAL','QUARANTINED','REJECTED')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by        UUID,
    updated_by        UUID,
    version           INT NOT NULL DEFAULT 1,
    audit_reference   TEXT,
    deleted_at        TIMESTAMPTZ,
    deleted_by        UUID,
    deletion_reason   TEXT
);

CREATE INDEX idx_goods_receipts_order ON goods_receipts (purchase_order_id);

SELECT ehos_make_history('goods_receipts');

GRANT USAGE ON SCHEMA public TO ehos_procurement_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_procurement_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_procurement_app;

COMMIT;