-- ============================================================================
-- EHOS  shared/00_db_roles.sql
-- Creates per-service application roles. Run ONCE as a superuser against
-- the `postgres` maintenance database before applying per-database DDL.
-- Idempotent.
-- ============================================================================

DO $$
DECLARE
    role_name text;
BEGIN
    FOR role_name IN SELECT unnest(ARRAY[
        'ehos_admin',                    -- DDL / migration owner
        'ehos_audit_app',
        'ehos_notification_app',
        'ehos_configuration_app',
        'ehos_identity_app',
        'ehos_patient_app',
        'ehos_scheduling_app',
        'ehos_ehr_app',
        'ehos_documentation_app',
        'ehos_prescription_app',
        'ehos_pharmacy_app',
        'ehos_laboratory_app',
        'ehos_radiology_app',
        'ehos_emergency_app',
        'ehos_surgery_app',
        'ehos_bed_app',
        'ehos_telemedicine_app',
        'ehos_workflow_app',
        'ehos_billing_app',
        'ehos_insurance_app',
        'ehos_finance_app',
        'ehos_inventory_app',
        'ehos_procurement_app',
        'ehos_hr_app',
        'ehos_payroll_app',
        'ehos_reporting_app',
        'ehos_ai_app',
        'ehos_knowledge_app'
    ]) LOOP
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format('CREATE ROLE %I NOLOGIN', role_name);
        END IF;
    END LOOP;
END $$;