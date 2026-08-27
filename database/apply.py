#!/usr/bin/env python
"""Apply EHOS database DDL per database-per-service standard.

For each service database it:
  1. optionally runs shared SQL (extensions, history trigger, outbox), and
  2. runs every versioned migration V*__*.sql (V001, V002, ...) in sorted order.

Usage:
    python database/apply.py [--host HOST] [--port PORT] [--user USER] [--password PASSWORD] [--skip-shared]
Requirements: psycopg2 (install: pip install psycopg2-binary)
"""

import argparse
import getpass
import os
from pathlib import Path

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

ROOT = Path(__file__).resolve().parent
SHARED = ROOT / "shared"

# database folder -> (db name, app role)
SERVICE_DATABASES = {
    "audit_db": ("ehos_audit", "ehos_audit_app"),
    "notification_db": ("ehos_notification", "ehos_notification_app"),
    "configuration_db": ("ehos_configuration", "ehos_configuration_app"),
    "identity_db": ("ehos_identity", "ehos_identity_app"),
    "patient_db": ("ehos_patient", "ehos_patient_app"),
    "scheduling_db": ("ehos_scheduling", "ehos_scheduling_app"),
    "ehr_db": ("ehos_ehr", "ehos_ehr_app"),
    "documentation_db": ("ehos_documentation", "ehos_documentation_app"),
    "prescription_db": ("ehos_prescription", "ehos_prescription_app"),
    "pharmacy_db": ("ehos_pharmacy", "ehos_pharmacy_app"),
    "laboratory_db": ("ehos_laboratory", "ehos_laboratory_app"),
    "radiology_db": ("ehos_radiology", "ehos_radiology_app"),
    "emergency_db": ("ehos_emergency", "ehos_emergency_app"),
    "surgery_db": ("ehos_surgery", "ehos_surgery_app"),
    "bed_db": ("ehos_bed", "ehos_bed_app"),
    "telemedicine_db": ("ehos_telemedicine", "ehos_telemedicine_app"),
    "workflow_db": ("ehos_workflow", "ehos_workflow_app"),
    "billing_db": ("ehos_billing", "ehos_billing_app"),
    "insurance_db": ("ehos_insurance", "ehos_insurance_app"),
    "finance_db": ("ehos_finance", "ehos_finance_app"),
    "inventory_db": ("ehos_inventory", "ehos_inventory_app"),
    "procurement_db": ("ehos_procurement", "ehos_procurement_app"),
    "hr_db": ("ehos_hr", "ehos_hr_app"),
    "payroll_db": ("ehos_payroll", "ehos_payroll_app"),
    "reporting_db": ("ehos_reporting", "ehos_reporting_app"),
    "ai_db": ("ehos_ai", "ehos_ai_app"),
    "knowledge_db": ("ehos_knowledge", "ehos_knowledge_app"),
    "analytics_db": ("ehos_analytics", "ehos_analytics_app"),
}

SHARED_FILES = ("01_extensions.sql", "02_history_trigger.sql", "03_outbox.sql")


def execute_script(connection, path: Path, label: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(path.read_text(encoding="utf-8"))
    print(f"applied {label}: {path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply EHOS database DDL")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user", default="ehos")
    parser.add_argument("--password", default=None)
    parser.add_argument("--skip-shared", action="store_true", help="skip shared/*.sql step")
    parser.add_argument("--only", default=None, help="apply only this database folder (e.g. patient_db)")
    args = parser.parse_args()

    password = args.password or getpass.getpass("PostgreSQL password for user %s: " % args.user)

    selected = SERVICE_DATABASES
    if args.only:
        if args.only not in SERVICE_DATABASES:
            raise SystemExit(f"unknown database folder: {args.only}")
        selected = {args.only: SERVICE_DATABASES[args.only]}

    for folder, (db_name, _role) in selected.items():
        migrations = sorted((ROOT / folder).glob("V*__*.sql"))
        if not migrations:
            print(f"SKIP {folder}: no versioned migrations (V001, ...)")
            continue

        try:
            connection = psycopg2.connect(
                host=args.host, port=args.port, user=args.user, password=password, dbname=db_name
            )
        except psycopg2.OperationalError as err:
            print(f"WARN {folder}: cannot connect to {db_name} ({err}). Create DBs first: python scripts/create_databases.py")
            continue

        connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        try:
            if not args.skip_shared:
                for shared_file in SHARED_FILES:
                    path = SHARED / shared_file
                    if path.exists():
                        execute_script(connection, path, f"{folder} shared/{shared_file}")
            for migration in migrations:
                execute_script(connection, migration, f"{folder}/{migration.name.split('__')[0]}")
        except Exception as err:  # noqa: BLE001 - surface per-db errors, continue others
            print(f"ERROR {folder}: {err}")
        finally:
            connection.close()


if __name__ == "__main__":
    main()