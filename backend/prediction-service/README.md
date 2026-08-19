# prediction-service

The **prediction-service** is EHOS's local-first, governed, advisory forecast
engine (PREDICTIVE_ANALYTICS_ARCHITECTURE.md). It trains forecast candidates
in-process (two offline adapters), registers them in `ai_db.ai_models`
(family `PREDICTION`) with a `model_evaluations` verdict, serves *approved*
models into the append-only `ai_db.predictions` lifecycle, and publishes
`PredictionGenerated` on `ai.prediction.generated` so agents (Inventory/HR/
Pharmacy/Executive) and dashboards react. Everything runs on hospital hardware
— no external/cloud model calls, and forecasts never trigger automatic
reorders, roster or spend changes.

## Forecast catalog (9 advisory targets)
Patient Inflow, Emergency Demand, Medicine Usage, Bed Occupancy, ICU Load,
Staffing, Revenue, Inventory Shortage, Equipment Maintenance — each with a
forecast metric and §5 status gate (`GET /api/v1/predictions/targets`).

## API (`/api/v1/predictions`)
| Method | Path | Purpose |
|---|---|---|
| GET | `/targets` | forecast catalog (entity/horizon/metric/gate) |
| POST | `/models/train` | P2+P3: backtest candidate, register model + evaluation |
| GET | `/models` · `/models/{key}` | registry |
| POST | `/models/{key}/approve` · `/reject` | owner approval gate |
| POST | `/generate` | P4: forecast -> VALID `predictions` row (supersedes same-window) |
| GET | `/lookup/{prediction_key}` | latest VALID forecast |
| GET | `` | list forecasts (filter by key/status) |
| POST | `/reconcile` | P5: actual-vs-forecast drift; flags stale models for retrain |

## Run
```bash
pip install -e ".[test]"
uvicorn prediction_service.main:app --port 8507
```
OpenAPI: `/docs`.

## Verify
```bash
python -m ruff check .
python -m pytest
# 17 tests (adapter/backtest/verdicts, lifecycle P2-P5, event publishing; in-memory SQLite)
```

## Environment
- `PREDICTION_DEFAULT_ADAPTER` = `seasonal_naive` | `ses`
- `PREDICTION_DEFAULT_PERIOD` (default 7), `PREDICTION_DEFAULT_HORIZON_STEPS` (default 7)
- `PREDICTION_DEFAULT_CONFIDENCE` (default 0.9)
- `KAFKA_BOOTSTRAP_SERVERS` (optional in local dev; eventing is best-effort)

## Database
Uses the existing `ehos_ai` schema (`database/ai_db/V001__init.sql`):
`ai_models`, `model_evaluations`, `predictions`. No new migration or database
required. Applied via `python database/apply.py --only ai_db`.

## Design notes
- Predictions are **append-only**: a new forecast for the same
  `prediction_key + window` retires the previous VALID row to `SUPERSEDED`.
- Only `APPROVED` models are serveable; a `builtin.seasonal_naive` fallback is
  used when no approved model exists yet (advisory only).
- Serving contract (`PREDICTIVE_ANALYTICS_ARCHITECTURE.md §8`):
  `{prediction_key, entity_type, entity_id, horizon, window_from/to, forecast
  {value,q10,q90}, confidence, model_version, generated_at, sources}`.