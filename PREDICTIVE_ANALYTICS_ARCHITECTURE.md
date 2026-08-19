# PREDICTIVE_ANALYTICS_ARCHITECTURE.md

# Enterprise Hospital Operating System (EHOS)

# Predictive Analytics — ML Architecture, Pipelines & Training Workflow

**Version:** 1.0.0
**Document Type:** Predictive ML Platform Design
**Audience:** ML Engineers, Data Engineers, AI Architects, Hospital Operations, Finance, Clinical Informatics

---

## 1. Purpose

EHOS Predictive Analytics turns historical hospital facts into forward-looking
estimates for planning and staffing. This document defines the **ML
architecture**, the **data/model/forecast pipelines**, and the **training
workflow** for the nine forecast targets:

| # | Forecast | Entity | Horizon | Primary consumers |
|---|---|---|---|---|
| 1 | Patient Inflow | department | daily · 7/30 day | Executive, scheduling |
| 2 | Emergency Demand | emergency department | hourly · 24–72 h | Emergency, HR |
| 3 | Medicine Usage | medication item | daily · 30 day | Pharmacy, Inventory |
| 4 | Bed Occupancy | ward | daily · 7 day | Bed mgmt, Executive |
| 5 | ICU Load | ICU units | daily · 7 day | ICU, Nursing, HR |
| 6 | Staff Requirement | department/role | shift · weekly | HR, Nursing |
| 7 | Revenue | charge/biller | monthly | Finance, Executive |
| 8 | Inventory Shortage | item | 7/30 day | Inventory, Procurement |
| 9 | Equipment Maintenance | asset | days-to-event | Facilities |

**Design constraint:** forecasts are **advisory only** — they never make
clinical or financial decisions automatically (AI_AGENT_ARCHITECTURE §2, §19;
ANALYTICS_DATA_WAREHOUSE_ARCHITEC §33).

### Governed elsewhere
| Concern | Document |
|---|---|
| Training/eval governance, model versioning | `AI_MODEL_DEVELOPMENT.md` |
| Warehouse & star-schema source data | `ANALYTICS_DATA_WAREHOUSE_ARCHITEC.md` |
| Event signals (features) | `EVENT_BUS.md`, `EVENT_BUS_SCHEMAS.md` |
| Predictions storage | `DATABASE_DESIGN.md` §8.1 `ai_db.predictions` |
| Forecast consumers (agents) | `SPECIALIZED_AI_AGENTS_ARCHITECTURE.md` |

---

## 2. Non-Negotiables

1. **Local-first training.** All training and inference run on hospital
   infrastructure with open-source libraries (sklearn, statsmodels, prophet-style
   or LightGBM); no external/cloud model calls.
2. **Feature provenance.** Every feature comes from a versioned dataset spec
   built from the event bus / warehouse; no ad-hoc feature drift.
3. **Temporal correctness.** Train/validation/test splits are **time-ordered**
   (never shuffled across time); no leakage from the future into features.
4. **Registered + approved models.** A forecast model is only served after
   evaluation passes and an owner approves it (`ai_models.approval_status`,
   `model_evaluations.verdict`).
5. **Append-only forecasts.** Every produced forecast is a row in
   `predictions` (status `VALID` → `SUPERSEDED`/`CANCELLED`); history is never
   rewritten.
6. **Evaluated in production.** Actuals are matched to forecasts; drift and
   error metrics trigger retraining; stale models are flagged.

---

## 3. ML Architecture

```
                 EHOS OPERATIONAL SERVICES (facts)
   patient · ehr · scheduling · pharmacy · inventory ·
   billing · hr · lab · radiology · emergency · equipment
                          │  events (Kafka, EVENT_BUS_SCHEMAS.md)
                          ▼
                  ┌─────────────────────┐
                  │   EVENT STREAM       │  raw facts (per-entity, keyed)
                  └──────────┬──────────┘
                             │ consume + aggregate
                             ▼
                  ┌─────────────────────┐      +-----------------------+
                  │  DATA WAREHOUSE      │─────▶│ FEATURE STORE         │
                  │  star schema facts   │      │ vetted feature specs, │
                  └──────────┬──────────┘      │ per forecast (offline) │
                             ▼                  └───────────┬───────────┘
                  ┌─────────────────────┐                          │
                  │ TRAINING ORCHESTRATOR (Airflow DAGs)          │
                  │  P0 ingest · P1 features · P2 train ·         │
                  │  P3 evaluate+register · P5 monitor            │
                  └──────────┬──────────┘                          │
                             ▼                                    │
                  ┌─────────────────────┐                          │
                  │ LOCAL MODEL TRAINING │  sklearn/statsmodels/    │
                  │ (GPU optional CPU-ok)│  lightgbm, offline       │
                  └──────────┬──────────┘                          │
                             ▼                                    │
                  ┌ ── MODEL REGISTRY ──┐  ai_db: ai_models         │
                  │ evaluate → approve →│ (family PREDICTION),      │
                  │ version + artifact  │ model_evaluations         │
                  └──────────┬──────────┘                          │
                             ▼                                     │
                  ┌ ─ PREDICTION SERVICE (port 8507) ─┐            │
                  │  refresh live features → forecast  │◀───────────┘
                  │  write ai_db.predictions           │
                  └──────────┬──────────┘
                             ▼
        PREDICTION-GENERATED event (ai.prediction.generated)
          → agents (Inventory/HR/Executive) · dashboards · alerts
```

- **Warehouse** = history; **event stream** = freshness. Models read features
  from the feature store (bulk) and refresh near-real-time signals from events.
- Training is **batch**; serving refreshes features periodically per horizon
  (daily/hourly).

---

## 4. Components

| Component | Role | Owning artifact |
|---|---|---|
| Event stream | normalized facts, per-entity keyed | Kafka (`EVENT_BUS_SCHEMAS.md` topics) |
| Data warehouse | star-schema history (visit/treatment/finance/inventory facts) | `ehos_analytics` |
| Feature store | versioned feature specs + materialized feature tables | prediction-service models + warehouse |
| Training orchestrator | schedules P0–P5 DAGs, retriggers on data/events | Airflow (local) |
| Model registry | `ai_models` PREDICTION rows + artifact refs + approval status | ai_db |
| Prediction service | forecast execution + lifecycle of `predictions` rows | prediction-service |
| Monitoring | actual-vs-forecast drift/eval, stale-model alerts | prediction-service + Grafana |
| Consumers | agents (inventory/hr/pharmacy/executive), dashboards | SPECIALIZED_AI_AGENTS |

---

## 5. Forecast Catalog (features, model, metric)

Per target: **features** (facts), **model family**, **metric**, **horizon**.

| Forecast | Key features (event/warehouse facts) | Model family | Primary metric | Status gate |
|---|---|---|---|---|
| Patient Inflow | `PatientAdmitted`, appointments, ED arrivals; hour·dow·month·holiday, dept, trend | gradient boosting / ETS | WAPE, MAE | < 20% WAPE @7d |
| Emergency Demand | `EmergencyTriggered`, arrivals, severity mix; hourly calendar | lightgbm / TBATS | WAPE (24h), MAE | < 25% @24h |
| Medicine Usage | `MedicationDispensed`, `StockConsumed`; med code, patient load | lightgbm / ARIMA | WAPE, MAE | < 20% @30d |
| Bed Occupancy | `PatientAdmitted`/`PatientDischarged`, LOS, transfers; ward | ETS / regression | MAE (beds), MAPE | ±15% @7d |
| ICU Load | ICU admissions, acuity (TISS), transfers; prior occupancy | tree / seasonal-naive | MAE (beds) | ±15% @7d |
| Staff Requirement | shift demand, forecast inflow/occupancy, `ShiftAssigned`, `LeaveApproved`, skill mix | XGBoost / poisson | MAE (FTE), coverage | ±10% per shift |
| Revenue | `BillGenerated`, `ChargeCreated`, `PaymentReceived`, claim status; case mix, rates | lightgbm / ARIMA | WAPE (monthly) | < 15% |
| Inventory Shortage | `StockLow`, `StockConsumed`, `StockReceived`, med dispense; reorder point, lead time | classifier (+count forecast) | Precision@k, recall | utilizer > 0.6@p10 |
| Equipment Maintenance | run-hours, fault events, age, prior maintenance, asset class | survival / time-to-event | days-error MAE | ±3 days @30d horizon |

`prediction_key` encodes `entity_type.horizon.model` e.g.
`bed_occupancy.daily.v3`; `forecast` JSON holds point + interval
(`{value, q10, q90, history_start}`).

---

## 6. Pipelines

### 6.1 P0 — Data ingestion
```
operational service → event → consume → validate envelope → idempotent insert
into warehouse facts (visit/treatment/finance/inventory) → dag success metric
```
- Idempotent by `eventId`; late events accepted up to a watermark; failures → DLQ per `EVENT_BUS_SCHEMAS.md` §6.

### 6.2 P1 — Feature engineering
```
feature spec (versioned YAML) → materialize feature table (per forecast target)
  ├─ calendar/date features (hour, dow, dow×dept, holiday, month)
  ├─ lag/rolling aggregates (7/14/30d sums, means, trends)
  ├─ exogenous (forecast inflow → staffing, occupancy → ICU, patient load → usage)
  └─ entity dims (dept, med class, ward, role, asset)
→ write feature table + dataset_version → register in metadata
```
- Each target has its own spec; specs are code-reviewed and versioned; reruns are deterministic (idempotent by `(spec_version, date_bucket, entity)`).

### 6.3 P2 — Training
```
load dataset_version → temporal split (train | val | test by time) →
drop leakage (features lag ≥1 step) → train candidate models →
save artifact → evaluate on VALIDATION → orchestrate tuning (folded backtest)
```
- Backtesting uses **expanding/rolling window** over history; never random split.

### 6.4 P3 — Evaluation + registration
```
holdout TEST evaluation → metrics vs status gate (§5) → model_evaluations(
  verdict PASS/WARN/FAIL, metrics) → registry ai_models approval_status:
  RAN → REVIEW → APPROVED (owner) → REJECTED
→ only APPROVED artifacts are serveable; WARN needs owner sign-off.
```

### 6.5 P4 — Forecast / serving pipeline
```
scheduled (per horizon: hourly/daily/weekly/monthly):
  refresh features (event lag ≤ freshness) → loader = approved artifact ref
  → predict point + interval → predict to ai_db.predictions
     (prediction_key, entity_type, entity_id, horizon, window_from/to,
      model_id, forecast JSONB, confidence) with status VALID
  → supersede same-key previous VALID rows → publish
     PredictionGenerated (ai.prediction.generated) to event bus
```
- Consumers: Inventory Agent reorder input, HR staffing input, Pharmacy,
  Executive briefs/dashboards. Retrieval is audited in `predictions` + agent
  runs (`ai-request` chain).

### 6.6 P5 — Monitoring / retraining loop
```
schedule actual-vs-forecast reconciliation:
  collect actuals (warehouse) → compute error vs last VALID forecasts
  → emit drift metrics → update ai_model status if stale/error beyond gate
  → trigger P2 retrain (with new data) → P3 → owner re-approval
```

```
P0 ─▶ P1 ─▶ P2 ─▶ P3 ─▶ P4(serve) ─▶ P5(monitor) ─┐
 ▲                          ▲                       │
 └─────────── trigger retrain ◀─────────────────────┘
```

---

## 7. Training Workflow

1. **Objective & dataset spec** — define target, entity, horizon, feature spec;
   confirm data owner + consent (governance gate; de-identification review for
   any clinical features).
2. **Data assembly (P0→P1)** — materialize features from warehouse + event
   stores; record `dataset_version` and provenance for every feature.
3. **Temporal split** — `train / validation / test` slices that respect time
   (e.g. last N periods held out); backtest windows defined.
4. **Baseline** — every task ships a simple baseline (seasonal-naive, mean,
   most-frequent) as a floor any ML model must beat.
5. **Model candidates** — offline libraries only; 2–3 families per task;
   hyperparameter search over validation via rolling backtest.
6. **Evaluation** — test metrics (§5), residual/interval calibration (q10/q90
   coverage), and **status gate** pass/fail.
7. **Registration & approval** — artifact + versioned `ai_models` row +
   `model_evaluations`; human owner approval before serving (approval levels 1–2;
   forecast recommendations are Level 2).
8. **Deployment** — prediction-service serves the approved artifact; features
   refresh scheduled per horizon; a shadow period compares new vs incumbent.
9. **Monitoring & retrain (P5)** — actual reconciliation, drift alerts,
   automatic retrain proposal on degraded performance; retrain re-enters at step 3.

---

## 8. Serving Contract

POST `/api/v1/predictions/query` (or internal invoke) returns:
```
{ prediction_key, entity_type, entity_id, horizon, window_from, window_to,
  forecast: { value, q10, q90 }, confidence, model_version,
  generated_at, sources: [feature refs] }
```
- Forecast rows are append-only (`predictions`); servicing replaces via
  `SUPERSEDED` status on the same `prediction_key + window`.
- Every forecast triggers `PredictionGenerated` on the bus so agents and
  dashboards react.

---

## 9. Integration with Agents

| Forecast | Agent/consumer action | Approval |
|---|---|---|
| Patient Inflow / ED Demand | Executive brief, HR demand signal | L1/L2 |
| Bed Occupancy / ICU Load | Executive situational, Bed mgmt | L1/L2 |
| Medicine Usage / Inventory Shortage | Pharmacy + Inventory reorder proposals | forecast L2 → reorder L3 |
| Staff Requirement | HR roster suggestions | forecast L2 → roster L2 |
| Revenue | Finance reviews / Executive digest | L1/L2 |
| Equipment Maintenance | Facilities work-order proposals | L2 |

Forecasts never auto-execute reorders, roster changes, or spend.

---

## 10. Governance & Security

- Training datasets are **de-identified or aggregated**; raw PHI never enters
  the feature store.
- Models/artifacts are immutable and versioned; every deployment is audited.
- Forecasts are advisory and clearly labeled ("model-based outlook, subject to
  verification"); no automatic clinical/financial action.
- All forecasting access is permission-scoped (role per target).

---

## 11. Implementation Mapping

| Artifact | Location / table |
|---|---|
| predictions | `ai_db.predictions` (existing) |
| model registry (PREDICTION) | `ai_db.ai_models` + `ai_db.model_evaluations` |
| feature store / dataset versions | prediction-service tables in `ehos_analytics` |
| prediction-service | new service (port 8507), consumes bus + warehouse APIs |
| orchestration | Airflow DAGs P0–P5 (local runners) |
| monitoring | Grafana/Prometheus (forecast error, drift, staleness) |
| event | `ai.prediction.generated` (topic `ai.*`) |
| docs | this doc + `AI_MODEL_DEVELOPMENT.md`, `ANALYTICS_DATA_WAREHOUSE_ARCHITEC.md` |

---

## 12. Final Principle

> Forecasts give the hospital a head start — never a substitute for
> judgment. Every prediction is local, governed, evaluated, and followed by an
> accountable human action.

# END OF PREDICTIVE ANALYTICS ARCHITECTURE