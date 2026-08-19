# Notification Service

EHOS outbound notification delivery (Phase 0).

## Responsibilities

- Template management with `{{variable}}` binding.
- Delivery via channel adapters: Email, SMS, Push, In-app.
- Consumes domain events (e.g. `AppointmentCreated`) to trigger notifications.
- Retry with up to 3 attempts per notification.

## Channel adapters

`channel/adapters.py` defines the `ChannelAdapter` interface. Phase 0 ships
stub adapters that log and return success so the pipeline works end-to-end.
Production providers plug in behind the same interface (no core changes).

## API

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/templates` | Create/update a template |
| GET | `/api/v1/templates/{key}` | Fetch a template |
| POST | `/api/v1/send` | Send a notification |
| GET | `/api/v1/health` | Health check |

## Events consumed

- `clinical.patient.registered` — routed to configured notifications.

## Local development

```bash
pip install -e ../../shared/ehos-common -e .
uvicorn notification_service.main:app --host 0.0.0.0 --port 8300
```

## Configuration

Environment variables per root `.env.example`. Provider credentials are handled
through the secrets manager, never committed to source.