-- ============================================================================
-- EHOS  shared/04_partman.sql
-- Optional pg_partman bootstrap for monthly partitioning of high-volume tables.
-- Requires pg_partman extension installed. Idempotent. Run per-database.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pg_partman WITH SCHEMA partman;

-- Register the tables that are partitioned by time.
-- Add a line per partitioned parent table in each database where it exists.
-- Examples (uncomment the ones that apply in the target database):
--
-- SELECT partman.create_parent('public.events',            'occurred_at', 'native', 'monthly');
-- SELECT partman.create_parent('public.audit_logs',        'occurred_at', 'native', 'monthly');
-- SELECT partman.create_parent('public.outbox_events',     'created_at',  'native', 'monthly');
-- SELECT partman.create_parent('public.vital_signs',       'recorded_at', 'native', 'monthly');
-- SELECT partman.create_parent('public.stock_movements',   'performed_at','native', 'monthly');
-- SELECT partman.create_parent('public.remote_monitoring_readings', 'captured_at', 'native', 'monthly');
-- SELECT partman.create_parent('public.samples',           'collection_time', 'native', 'monthly');
--
-- UPDATE partman.part_config SET retention = '6 months'  WHERE parent_table = 'public.outbox_events';
-- UPDATE partman.part_config SET retention = '7 years'   WHERE parent_table = 'public.audit_logs';
-- UPDATE partman.part_config SET retention = '13 months' WHERE parent_table = 'public.vital_signs';
--
-- Then schedule via pg_cron or an external job every hour:
-- SELECT partman.run_maintenance();