# executive-dashboard (EHOS Executive Command Center)

Real-time hospital executive dashboard built on the EHOS AI platform:
live KPIs, advisory forecasts from the **prediction-service** and executive
briefings from the **ai-service** (HospitalGPT), with interactive charts and
offline PDF/Excel export.

## Features
- **Real-time KPIs** — Admissions, Discharges, Revenue, Expenses, Bed Occupancy,
  Waiting Time, Staff Utilization, Inventory, Mortality, Readmission; every card
  shows the current value, period-over-period delta, status (ok/warn/alert) and
  a sparkline. Auto-refreshes (5s/15s/60s/paused).
- **Interactive charts** — dependency-free SVG charts with hover crosshair +
  tooltips: admissions vs discharges (line), revenue vs expenses (grouped bars),
  occupancy & staff utilisation (multi-line), waiting time (72h).
- **Advisory forecasts** — reads the prediction-service serving contract
  (`GET /api/v1/predictions/lookup/{key}`) for patient-inflow, bed-occupancy,
  ICU-load, revenue and medicine-usage, rendered as band charts (value + q10/q90).
  Falls back to deterministic sample forecasts when the service is offline.
- **AI insights** — posts the KPI snapshot to HospitalGPT
  (`POST /api/v1/ai/chat`) for an executive briefing; falls back to rule-based
  insights when the ai-service is unavailable.
- **Export PDF** — print-optimised layout via the browser print dialog.
- **Export Excel** — dependency-free SpreadsheetML workbook (KPIs, Trends,
  Forecasts, AI Insights) that opens in Excel.

## Run
```bash
npm install
npm run dev        # http://localhost:5176
```
Backends (optional; the dashboard degrades to demo data):
- `uvicorn prediction_service.main:app --port 8507`
- `uvicorn ai_service.main:app --port 8506`

## Verify
```bash
npm run build      # tsc -b && vite build
```
(Dev-only note: on this machine run with `npm_config_script_shell=` if a stale
shell env breaks `npm run`.)

## Data provenance
KPI values are produced by the dashboard's deterministic demo engine
(`src/lib/demo.ts` — seeded mulberry32, internally-consistent admissions →
census → discharges → revenue/expenses → workforce/inventory/outcomes) until an
analytics service exposes live aggregates. Forecasts are **advisory only**
(PREDICTIVE_ANALYTICS_ARCHITECTURE §10) and never trigger automatic actions.