-- ============================================================================
-- EHOS  inventory_db  V001__init.sql
-- inventory-service: items, stock, movements, reorder alerts.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- items — item catalog
-- ----------------------------------------------------------------------------
CREATE TABLE items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sku             TEXT NOT NULL,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL,
    unit_of_measure TEXT NOT NULL,
    unit_cost       NUMERIC(12,2),
    reorder_point   INT NOT NULL DEFAULT 0,
    reorder_qty     INT NOT NULL DEFAULT 0,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID,
    updated_by      UUID,
    version         INT NOT NULL DEFAULT 1,
    status          TEXT NOT NULL,
    audit_reference TEXT,
    deleted_at      TIMESTAMPTZ,
    deleted_by      UUID,
    deletion_reason TEXT
);

CREATE UNIQUE INDEX uq_items_sku ON items (sku) WHERE deleted_at IS NULL;
CREATE INDEX idx_items_category ON items (category);

-- ----------------------------------------------------------------------------
-- stock_items — location-based stock with lot/expiry tracking
-- ----------------------------------------------------------------------------
CREATE TABLE stock_items (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id           UUID NOT NULL REFERENCES items(id),
    location          TEXT NOT NULL,
    lot_number        TEXT,
    expiry_date       TIMESTAMPTZ,
    quantity_on_hand  INT NOT NULL DEFAULT 0 CHECK (quantity_on_hand >= 0),
    quantity_reserved INT NOT NULL DEFAULT 0,
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

CREATE UNIQUE INDEX uq_stock_item_loc_lot ON stock_items (item_id, location, lot_number) WHERE deleted_at IS NULL;
CREATE INDEX idx_stock_items_item ON stock_items (item_id);
CREATE INDEX idx_stock_items_location ON stock_items (location);
CREATE INDEX idx_stock_items_expiry ON stock_items (expiry_date) WHERE expiry_date IS NOT NULL;

-- ----------------------------------------------------------------------------
-- stock_movements — receipt, dispense, transfer, adjustment, write-off, return
-- ----------------------------------------------------------------------------
CREATE TABLE stock_movements (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_item_id   UUID NOT NULL REFERENCES stock_items(id),
    movement_type   TEXT NOT NULL CHECK (movement_type IN ('RECEIPT','DISPENSE','TRANSFER','ADJUSTMENT','WRITE_OFF','RETURN')),
    quantity        INT NOT NULL CHECK (quantity > 0),
    reference_type  TEXT,
    reference_id    UUID,
    reason          TEXT,
    performed_by    UUID NOT NULL,
    performed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID,
    updated_by      UUID,
    version         INT NOT NULL DEFAULT 1,
    status          TEXT NOT NULL,
    audit_reference TEXT,
    deleted_at      TIMESTAMPTZ,
    deleted_by      UUID,
    deletion_reason TEXT
);

CREATE INDEX idx_movements_stock ON stock_movements (stock_item_id);
CREATE INDEX idx_movements_type ON stock_movements (movement_type);
CREATE INDEX idx_movements_performed ON stock_movements (performed_at DESC);

-- ----------------------------------------------------------------------------
-- reorder_alerts — auto-generated when stock hits reorder point
-- ----------------------------------------------------------------------------
CREATE TABLE reorder_alerts (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id          UUID NOT NULL REFERENCES items(id),
    location         TEXT NOT NULL,
    quantity_on_hand INT NOT NULL,
    reorder_point    INT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'OPEN',
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

CREATE INDEX idx_reorder_item ON reorder_alerts (item_id);
CREATE INDEX idx_reorder_location ON reorder_alerts (location);
CREATE INDEX idx_reorder_status ON reorder_alerts (status);

-- ----------------------------------------------------------------------------
-- history tables
-- ----------------------------------------------------------------------------
SELECT ehos_make_history('items');
SELECT ehos_make_history('stock_items');
SELECT ehos_make_history('stock_movements');
SELECT ehos_make_history('reorder_alerts');

-- ----------------------------------------------------------------------------
-- grants
-- ----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO ehos_inventory_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_inventory_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_inventory_app;

COMMIT;
