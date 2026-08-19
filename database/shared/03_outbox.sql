-- ============================================================================
-- EHOS  shared/03_outbox.sql
-- Transactional outbox table. Created in EVERY database with exactly this
-- shape so the ehos-common outbox + Kafka producer can reuse one contract.
-- Partitioned by created_at (monthly). Idempotent.
-- ============================================================================

CREATE TABLE IF NOT EXISTS outbox_events (
    id             UUID NOT NULL DEFAULT gen_random_uuid(),
    event_id       UUID NOT NULL,
    event_type     TEXT NOT NULL,
    event_version  INT  NOT NULL DEFAULT 1,
    source         TEXT NOT NULL,
    correlation_id TEXT,
    user_id        UUID,
    payload        JSONB NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    status         TEXT NOT NULL DEFAULT 'PENDING'
                   CHECK (status IN ('PENDING','PUBLISHED','FAILED','DEAD_LETTER')),
    published_at   TIMESTAMPTZ,
    attempts       INT  NOT NULL DEFAULT 0,
    last_error     TEXT,
    PRIMARY KEY (id, created_at),
    UNIQUE (event_id, created_at)
) PARTITION BY RANGE (created_at);
-- NOTE: Postgres requires PRIMARY KEY / UNIQUE to include the partition key,
-- hence (id, created_at) and (event_id, created_at).

CREATE TABLE IF NOT EXISTS outbox_events_default PARTITION OF outbox_events FOR VALUES FROM (MINVALUE) TO (MAXVALUE);

CREATE INDEX IF NOT EXISTS idx_outbox_pending
    ON outbox_events (status, created_at) WHERE status = 'PENDING';

-- pg_partman (when installed) will manage monthly sub-partitions:
-- SELECT partman.create_parent('public.outbox_events', 'created_at', 'native', 'monthly');
-- UPDATE partman.part_config SET retention = '3 months' WHERE parent_table = 'public.outbox_events';