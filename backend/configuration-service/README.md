# Configuration Service

EHOS reference configuration and feature-flag service (Phase 0).

## Responsibilities

- Feature flags (create, list, enable/disable).
- Versioned key/value reference configuration (e.g. `appointment_slot_min`).
- Redis cache for low-latency reads.
- Emits `ConfigurationUpdated` events on `configuration.topic` when entries change.

## API

OpenAPI schema is served live at `http://localhost:8100/docs` (Swagger) and
`/api/v1/openapi.json`. A static `openapi.yaml` is committed in this directory.

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/flags` | Create a feature flag |
| GET | `/api/v1/flags` | List feature flags |
| PATCH | `/api/v1/flags/{name}` | Enable/disable a flag |
| PUT | `/api/v1/entries/{config_key}` | Create/update a configuration entry |
| GET | `/api/v1/entries` | List all entries |
| GET | `/api/v1/entries/{config_key}` | Get a single entry |
| GET | `/api/v1/all` | Aggregate snapshot (flags + entries) for service bootstrap |

## Events

- **Topic:** `configuration.topic`
- **Event:** `ConfigurationUpdated` — `payload: {configKey, value}`

Consumers must be idempotent (CODING_STANDARDS.md §17).

## Local development

```bash
python -m venv .venv
pip install -e ../../shared/ehos-common -e .
uvicorn config_service.main:app --host 0.0.0.0 --port 8100
```

Run tests:

```bash
python -m pytest -q
```

## Configuration

All configuration derives from environment variables (see root `.env.example`).
Secrets are never committed and never logged (CODING_STANDARDS.md §14, §15).