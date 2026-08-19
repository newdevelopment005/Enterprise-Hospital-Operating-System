-- ============================================================================
-- EHOS  shared/01_extensions.sql
-- Required extensions. MUST run in every database before table DDL.
-- Postgres 16+; idempotent.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;      -- gen_random_uuid(), crypt()
CREATE EXTENSION IF NOT EXISTS pg_trgm;       -- trigram similarity indexes
-- Optional, uncomment per environment:
-- CREATE EXTENSION IF NOT EXISTS pg_partman;   -- monthly partition mgmt
-- CREATE EXTENSION IF NOT EXISTS timescaledb;  -- only for dedicated vitals DB