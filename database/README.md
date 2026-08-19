# Database Migrations & Provisioning

EHOS database baseline. Each service owns exactly one database (`database-per-service`).
This directory holds the executable PostgreSQL DDL that implements `DATABASE_DESIGN.md`.

## Layout

```
database/
├── README.md
├── shared/
│   ├── 00_db_roles.sql             # app/ddl roles per service (run once as superuser)
│   ├── 01_extensions.sql           # pgcrypto, pg_trgm (required in every DB)
│   ├── 02_history_trigger.sql      # generic history trigger fn (run in every DB)
│   ├── 03_outbox.sql               # outbox_events table (run in every DB)
│   └── 04_partman.sql              # pg_partman scheduled partitioning (optional)
├── <service>_db/
│   └── V001__init.sql              # schema for that service (Flyway/Alembic versioned)
└── apply.py                        # applies shared + V001 to each database
```

## Rules

- **Every DB** must run `01_extensions.sql`, `02_history_trigger.sql`, `03_outbox.sql`.
- **No cross-database FK references.** FKs stay inside one database.
- Every business table uses the common block from `DATABASE_DESIGN.md` §2.5.
- Every business table gets a `<table>_history` table and a trigger.
- Clinical + financial tables are **never hard-deleted**; only soft delete + audit.

## Applying

```bash
python scripts/create_databases.py                      # creates all <service>_db
python database/apply.py --host localhost --user ehos   # applies DDL to each db
```

Versioning: migrations follow Flyway style `V001__...sql`; app-side Alembic generates
`alembic/versions/` from these. Migrations are tested and reversible in dev.