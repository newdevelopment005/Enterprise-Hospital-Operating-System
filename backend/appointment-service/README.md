# EHOS appointment-service

Patient appointment booking for the hospital (scheduling_db / `appointments`).

## Responsibilities

- Book, reschedule, cancel, complete and no-show appointments
- Provider and patient double-booking prevention (HTTP 409)
- Free-slot availability grid per clinic day (settings-driven hours)
- Publishes `AppointmentCreated` / `AppointmentRescheduled` /
  `AppointmentCancelled` / `AppointmentCompleted` on `clinical.appointment.*`
  via the transactional outbox (published only after the DB commit)

## API (prefix `/api/v1/appointments`)

| Method | Path | Purpose |
|---|---|---|
| POST | `` | Book an appointment |
| GET | `` | List/filter (`patient_id`, `provider_id`, `status`, `from`, `to`, `upcoming`) |
| GET | `/availability?day=YYYY-MM-DD` | Free slot grid |
| GET | `/{id}` | Fetch one |
| POST | `/{id}/reschedule` | Move to a new slot |
| POST | `/{id}/cancel` | Cancel with optional reason |
| POST | `/{id}/complete` | Mark completed |
| POST | `/{id}/no-show` | Mark no-show |

Port: 8503. Gateway route: `/api/v1/appointments` → `appointment-service:8503`.

## Run tests

```bash
python -m venv .venv
. .venv/Scripts/activate  # or source .venv/bin/activate
pip install -e ../../shared/ehos-common -e ".[test]"
pytest -q
ruff check src tests
```
