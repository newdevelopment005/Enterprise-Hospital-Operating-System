#!/usr/bin/env python
"""Create the EHOS development database per database-per-service standard.

Creates one database for each service plus supporting databases. Idempotent.
Usage:
    python scripts/create_databases.py [--host HOST] [--port PORT] [--user USER] [--password PASSWORD]
"""

import argparse
import getpass

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

DATABASES = (
    "ehos",                       # shared/dev database
    "ehos_keycloak",              # Keycloak store
    "ehos_gateway",               # api-gateway workshop/route state
    # platform
    "ehos_audit",
    "ehos_notification",
    "ehos_configuration",
    "ehos_identity",
    # patient & scheduling
    "ehos_patient",
    "ehos_scheduling",
    # clinical
    "ehos_ehr",
    "ehos_documentation",
    "ehos_prescription",
    "ehos_pharmacy",
    "ehos_laboratory",
    "ehos_radiology",
    "ehos_emergency",
    "ehos_surgery",
    "ehos_bed",
    "ehos_telemedicine",
    "ehos_workflow",
    # operations / enterprise
    "ehos_billing",
    "ehos_insurance",
    "ehos_finance",
    "ehos_inventory",
    "ehos_procurement",
    "ehos_hr",
    "ehos_payroll",
    "ehos_reporting",
    # AI
    "ehos_ai",
    "ehos_knowledge",
    # analytics warehouse (separate design; created early for infra parity)
    "ehos_analytics",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create EHOS development databases")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user", default="ehos")
    parser.add_argument("--password", default=None)
    args = parser.parse_args()

    password = args.password or getpass.getpass("PostgreSQL password for user %s: " % args.user)

    connection = psycopg2.connect(host=args.host, port=args.port, user=args.user, password=password, dbname="postgres")
    connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    with connection.cursor() as cursor:
        cursor.execute("SELECT datname FROM pg_database")
        existing = {row[0] for row in cursor.fetchall()}
        for db_name in DATABASES:
            if db_name not in existing:
                cursor.execute(f'CREATE DATABASE "{db_name}"')
                print(f"created database {db_name}")
            else:
                print(f"database {db_name} already exists")
    connection.close()


if __name__ == "__main__":
    main()