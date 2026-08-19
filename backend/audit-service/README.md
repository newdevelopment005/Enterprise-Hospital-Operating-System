# Audit Service

EHOS immutable audit trail (Phase 0).

## Responsibilities

- Append-only audit records with SHA-256 hash-chain integrity.
- Consumption of `audit.topic` events from all services.
- Integrity verification endpoint for tamper detection.
- Legally retained, never physically deleted (DATABASE_STANDARDS.md).

## Integrity model

Each record stores `content_hash` computed over its logical content plus the
`previous_hash`. Any modification of a historical record breaks the chain and
is detected by `GET /api/v1/integrity`.

## API

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/records` | Append an audit record |
| GET | `/api/v1/records/{id}` | Fetch a record |
| GET | `/api/v1/records` | Search records (filters + pagination) |
| GET | `/api/v1/integrity` | Verify hash-chain integrity |

## Events consumed

- **Topic:** `audit.topic`
- Records are idempotently de-duplicated by `eventId`.

## Local development

```bash
python -m venv .venv
pip install -e ../../shared/ehos-common -e .
uvicorn audit_service.main:app --host 0.0.0.0 --port 8200
```

Tests:

```bash
python -m pytest -q
```

## Configuration

Environment variables per root `.env.example`. Never log authentication tokens,
secrets, or full patient records (CODING_STANDARDS.md section 14).