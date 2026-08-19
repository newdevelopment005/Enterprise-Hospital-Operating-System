-- ============================================================================
-- EHOS  inventory_db / V001__init.sql
-- Service: inventory-service
-- Description: Baseline schema for the inventory database: inventory items,
--   an append-only stock_movements ledger partitioned by RANGE (performed_at),
--   and stock_levels location/batch snapshots. stock_movements is an immutable
--   ledger (never UPDATE, only append) and, being partitioned, skips the per-row
--   history trigger.
-- Design: DATABASE_DESIGN.md sections 2, 7.4, 2.8, 2.9, 9, 10.
-- Requires: shared 01_extensions.sql (pgcrypto, pg_trgm), 02_history_trigger.sql
--   (fn_append_history(), ehos_make_history()), 03_outbox.sql (outbox_events)
--   applied first by apply.py. No \i includes in this file.
-- Postgres 16+, lowercase snake_case, app role: ehos_inventory_app.
-- ============================================================================

BEGIN;

CREATE TABLE inventory_items (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code           TEXT NOT NULL,
    item_name      TEXT NOT NULL,
    category       TEXT NOT NULL,
    sub_category   TEXT,
    unit           TEXT NOT NULL,
    reorder_level  NUMERIC NOT NULL DEFAULT 0,
    reorder_qty    NUMERIC NOT NULL DEFAULT 0,
    avg_cost       NUMERIC(12,2),
    is_consumable  BOOLEAN NOT NULL DEFAULT true,
    attributes     JSONB,
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

CREATE UNIQUE INDEX uq_inventory_items_code ON inventory_items (code) WHERE deleted_at IS NULL;
CREATE INDEX idx_inventory_items_name_trgm ON inventory_items USING gin (item_name gin_trgm_ops);
CREATE INDEX idx_inventory_items_category ON inventory_items (category);

SELECT ehos_make_history('inventory_items');

CREATE TABLE stock_movements (
    id            UUID NOT NULL DEFAULT gen_random_uuid(),
    item_id       UUID NOT NULL REFERENCES inventory_items(id),
    location      TEXT NOT NULL,
    batch_number  TEXT,
    movement_type TEXT NOT NULL CHECK (movement_type IN ('RECEIVED','CONSUMED','TRANSFER_OUT','TRANSFER_IN','RETURN','ADJUSTMENT','EXPIRED','DISPOSED')),
    quantity      NUMERIC NOT NULL,
    unit_cost     NUMERIC(12,2),
    performed_by  UUID NOT NULL,
    performed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ref_type      TEXT,
    ref_id        UUID,
    balance_after NUMERIC NOT NULL,
    reason        TEXT,
    -- PG16 requires PK on partitioned tables to include the partition key:
    PRIMARY KEY (id, performed_at),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by    UUID,
    updated_by    UUID,
    version       INT NOT NULL DEFAULT 1,
    status        TEXT NOT NULL DEFAULT 'POSTED' CHECK (status IN ('POSTED')),
    audit_reference TEXT,
    deleted_at    TIMESTAMPTZ,
    deleted_by    UUID,
    deletion_reason TEXT
) PARTITION BY RANGE (performed_at);

CREATE TABLE stock_movements_default PARTITION OF stock_movements FOR VALUES FROM (MINVALUE) TO (MAXVALUE);

CREATE INDEX idx_stock_movements_item ON stock_movements (item_id, performed_at DESC) WHERE deleted_at IS NULL;

CREATE TABLE stock_levels (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id       UUID NOT NULL REFERENCES inventory_items(id),
    location      TEXT NOT NULL,
    batch_number  TEXT,
    quantity      NUMERIC NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    reserved      NUMERIC NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    expiry_date   DATE,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by    UUID,
    updated_by    UUID,
    version       INT NOT NULL DEFAULT 1,
    status        TEXT NOT NULL,
    audit_reference TEXT,
    deleted_at    TIMESTAMPTZ,
    deleted_by    UUID,
    deletion_reason TEXT
);

CREATE UNIQUE INDEX uq_stock_levels_item_location_batch
    ON stock_levels (item_id, location, batch_number)
    WHERE deleted_at IS NULL;
CREATE INDEX idx_stock_levels_expiry ON stock_levels (expiry_date) WHERE deleted_at IS NULL AND quantity > 0;

SELECT ehos_make_history('stock_levels');

GRANT USAGE ON SCHEMA public TO ehos_inventory_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_inventory_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_inventory_app;

COMMIT;