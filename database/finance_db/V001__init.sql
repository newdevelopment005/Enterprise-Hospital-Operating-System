-- ============================================================================
-- EHOS  finance_db / V001__init.sql
-- Service: finance-service
-- Description: Baseline schema for the finance (double-entry GL) database:
--   chart of accounts, accounting periods, journal entries and journal lines.
--   Financial integrity matters: balanced-entry enforcement happens in the app
--   layer; journal_lines_history is essential for GL audit.
-- Design: DATABASE_DESIGN.md sections 2, 7.3, 9, 10.
-- Requires: shared 01_extensions.sql (pgcrypto, pg_trgm), 02_history_trigger.sql
--   (fn_append_history(), ehos_make_history()), 03_outbox.sql (outbox_events)
--   applied first by apply.py. No \i includes in this file.
-- Postgres 16+, lowercase snake_case, app role: ehos_finance_app.
-- ============================================================================

BEGIN;

CREATE TABLE accounts (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code          TEXT NOT NULL,
    name          TEXT NOT NULL,
    account_type  TEXT NOT NULL CHECK (account_type IN ('ASSET','LIABILITY','EQUITY','REVENUE','EXPENSE')),
    parent_id     UUID REFERENCES accounts(id),
    is_control    BOOLEAN NOT NULL DEFAULT false,
    status        TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE','CLOSED')),
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

CREATE UNIQUE INDEX uq_accounts_code ON accounts (code) WHERE deleted_at IS NULL;
CREATE INDEX idx_accounts_parent ON accounts (parent_id);

SELECT ehos_make_history('accounts');

CREATE TABLE accounting_periods (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    period_key TEXT NOT NULL,
    starts_on  DATE NOT NULL,
    ends_on    DATE NOT NULL,
    status     TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','CLOSING','CLOSED')),
    closed_by  UUID,
    closed_at  TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by UUID,
    updated_by UUID,
    version    INT NOT NULL DEFAULT 1,
    audit_reference TEXT,
    deleted_at TIMESTAMPTZ,
    deleted_by UUID,
    deletion_reason TEXT
);

CREATE UNIQUE INDEX uq_accounting_periods_period_key ON accounting_periods (period_key) WHERE deleted_at IS NULL;

SELECT ehos_make_history('accounting_periods');

CREATE TABLE journal_entries (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    journal_no     TEXT NOT NULL,
    period_id      UUID NOT NULL REFERENCES accounting_periods(id),
    entry_date     DATE NOT NULL DEFAULT CURRENT_DATE,
    source         TEXT NOT NULL,
    source_ref     UUID,
    description    TEXT,
    posted_at      TIMESTAMPTZ,
    posted_by      UUID,
    status         TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','POSTED','REVERSED')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by     UUID,
    updated_by     UUID,
    version        INT NOT NULL DEFAULT 1,
    audit_reference TEXT,
    deleted_at     TIMESTAMPTZ,
    deleted_by     UUID,
    deletion_reason TEXT
);

CREATE UNIQUE INDEX uq_journal_entries_journal_no ON journal_entries (journal_no) WHERE deleted_at IS NULL;
CREATE INDEX idx_journal_entries_period ON journal_entries (period_id);

SELECT ehos_make_history('journal_entries');

CREATE TABLE journal_lines (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    journal_entry_id UUID NOT NULL REFERENCES journal_entries(id),
    account_id       UUID NOT NULL REFERENCES accounts(id),
    debit            NUMERIC(14,2) NOT NULL DEFAULT 0,
    credit           NUMERIC(14,2) NOT NULL DEFAULT 0,
    description      TEXT,
    cost_center_id   UUID,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       UUID,
    updated_by       UUID,
    version          INT NOT NULL DEFAULT 1,
    status           TEXT NOT NULL,
    audit_reference  TEXT,
    deleted_at       TIMESTAMPTZ,
    deleted_by       UUID,
    deletion_reason  TEXT,
    CHECK (debit >= 0),
    CHECK (credit >= 0),
    CHECK (NOT (debit = 0 AND credit = 0))
);

CREATE INDEX idx_journal_lines_entry ON journal_lines (journal_entry_id);
CREATE INDEX idx_journal_lines_account ON journal_lines (account_id);

SELECT ehos_make_history('journal_lines');

GRANT USAGE ON SCHEMA public TO ehos_finance_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ehos_finance_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehos_finance_app;

COMMIT;