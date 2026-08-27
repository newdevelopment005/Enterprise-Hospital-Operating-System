# EHOS — IT Engineer Guide

Technical installation, download and run book for **EHOS (Enterprise Hospital
Operating System)** — an AI-native, event-driven, offline-first hospital
operating system built on a Python/FastAPI microservice platform with React
frontends, PostgreSQL, Kafka, Redis, MinIO and Keycloak.

This document is aimed at system/DevOps engineers who will install, configure,
run, monitor and troubleshoot the platform. For a plain-language overview of the
modules and workflows, see `USER_GUIDE.md`.

---

## 1. Architecture at a glance

- **Service-oriented monorepo**: 23 Python/FastAPI services + 1 shared library
  (`shared/ehos-common`), each with its own database (`database-per-service`).
- **Single entry point**: `api-gateway` (`:8000`) owns routing, JWT validation
  and rate limiting; it also maps short frontend prefixes (`/mpi`, `/sched`,
  `/lab`, …) to canonical `/api/v1/*` paths.
- **Event bus**: Kafka (topics auto-created). Services publish canonical events
  (e.g. `clinical.patient.registered`) via a publish-after-commit outbox.
- **Identity**: two paths — Keycloak (`identity-service`, realm `ehos`) for the
  gateway + AI JWKS validation, and an in-repo `authentication-service` with
  sessions, TOTP MFA, lockout and password policy. See §10 for the important
  caveat about the two paths.
- **AI / analytics**: offline stack — `knowledge-service` (RAG), `ai-service`
  (HospitalGPT chat, STT/TTS/OCR), `prediction-service` (forecasting),
  `analytics-service` (data warehouse + dashboards). Optional Opt-in Ollama for
  real local inference/embeddings (defaults are `mock`).
- **Frontends**: 4 React + TypeScript + Vite apps.

```
Browser apps ──► api-gateway :8000 ──► upstream services (Kafka events / Postgres per service)
                  │  ▲
                  │  └── Keycloak :8400 (JWKS) · Redis · MinIO · Kafka :9092
```

---

## 2. Repository layout

```text
backend/
  api-gateway/                      # :8000  single entry point
  identity-service/                 # Keycloak realm definition (config only)
  configuration-service/            # :8100  feature flags / reference config
  audit-service/                    # :8200  tamper-evident audit trail
  notification-service/             # :8300  SMS / email / push notifications
  authentication-service/           # :8500  internal IAM (MFA, sessions, RBAC)
  patient-service/                  # :8501  MPI demographics, merge, alerts
  ehr-service/                      # :8502  clinical record (notes, vitals, orders…)
  appointment-service/              # :8503  scheduling
  queue-service/                    # :8504  digital queues / tickets
  knowledge-service/                # :8505  RAG documents, corpora, embeddings
  ai-service/                       # :8506  HospitalGPT (chat, agents, media facades)
  prediction-service/               # :8507  offline forecasting
  analytics-service/                # :8508  warehouse metrics + dashboards
  billing-service/                  # :8509  charges, invoices, payments
  prescription-service/             # :8510  prescribing, MAR, allergies
  pharmacy-service/                 # :8511  medication catalog / stock / dispensing
  laboratory-service/               # :8512  test catalog / orders / samples / results
  radiology-service/                # :8513  modalities / orders / studies / reports
  inventory-service/                # :8514  items / stock / movements / alerts
  workflow-service/                 # :8515  workflow engines / instances / transitions
  clinical-documentation-service/   # :8516  notes / versions / templates
  insurance-service/                # :8517  coverages / claims / prior auths
  reporting-service/                # :8518  report definitions / instances / schedules
shared/ehos-common/                 # cross-cutting Python library (editable install)
frontend/apps/
  patient-registration/             # :5173  intake
  ehr-portal/                       # :5174  clinical chart
  ai-assistant/                     # :5175  HospitalGPT chat UI
  executive-dashboard/              # :5176  KPI / command center
database/                           # DDL migrations + apply.py + shared roles
infrastructure/                     # docker-compose.yml (+ optional override)
monitoring/                         # Prometheus / Grafana / Loki / Tempo
security/ · scripts/ · .github/     # policies, helpers, CI
```

---

## 3. Prerequisites

| Requirement | Minimum | Notes |
|---|---|---|
| Git | any | to clone the repository |
| Docker + Compose v2 | current | recommended run path (Option A) |
| Python | 3.11+ (3.13 tested) | bare-metal path (Option B) + tooling |
| Node.js + npm | 18+ | frontend apps |
| `make` | any | Linux/macOS/WSL convenience targets |
| `psycopg2`/`psycopg` | latest | `scripts/create_databases.py` (Option B) |
| Ollama (optional) | — | local LLM + embedding models for the AI stack |

Ports used by the platform (must be free unless remapped, see §6.3):

| Port(s) | Component |
|---|---|
| 8000 | api-gateway |
| 8100 / 8200 / 8300 | configuration / audit / notification |
| 8400 | Keycloak (published; container listens on 8080) |
| 8500–8518 | the 19 service application ports below |
| 5432, 6379, 9092, 9000, 9001 | PostgreSQL / Redis / Kafka / MinIO / MinIO console |
| 5173–5176 | frontend dev servers |
| 9090 / 3000 / 3100 / 3200 | monitoring profile: Prometheus / Grafana / Loki / Tempo |
| 11434 | Ollama (host, optional) |

---

## 4. Download the system

```bash
git clone https://github.com/newdevelopment005/Enterprise-Hospital-Operating-System.git
cd "Enterprise-Hospital-Operating-System"
```

The repository is "Phase 0: Foundation Platform" plus the operational and AI
modules (see `CHANGELOG.md`). Everything needed to run is inside the repo —
there is nothing else to download except optional Ollama models.

---

## 5. Configure the environment

1. Create the environment file (never commit the real one — `.env` is
   git-ignored):

   ```bash
   make init        # copies .env.example → .env, creates data/minio + data/postgres
   ```

   or manually:

   ```bash
   cp .env.example .env
   ```

2. Open `.env` and replace every `change-me`/`ehos-dev-only` value:
   - `POSTGRES_USER` / `POSTGRES_PASSWORD`
   - `KEYCLOAK_ADMIN_PASSWORD` (also used as the `ehos` realm admin password,
     dev default `Ehos-Admin-2026`), `KEYCLOAK_CLIENT_SECRET`
   - `MINIO_ROOT_PASSWORD`
   - `GRAFANA_ADMIN_PASSWORD` (monitoring profile)

> The shared settings **fail fast** if `EHOS_ENV` is not `development` while a
> default password is still in use.

---

## 6. Run path A — full stack with Docker Compose (recommended)

### 6.1 Build and start

```bash
make build         # docker compose build (first run is the slow one)
make up            # start the full stack in the background
make ps            # wait until containers are healthy
make logs          # tail all logs (Ctrl-C to stop)
```

All application services are packaged as images via their per-service
`Dockerfile`s and are included in `infrastructure/docker-compose.yml`. Keycloak
imports the `ehos` realm automatically on first start.

### 6.2 Useful targets

| Command | Purpose |
|---|---|
| `make down` | stop the stack (volumes are kept) |
| `make kafka-topics` | list event-bus topics |
| `make migrate` | apply SQL migrations (`python database/apply.py`) |
| `make test` | run every backend service test suite |
| `make lint` | ruff lint every service + `ehos-common` |
| `docker compose --profile monitoring up -d` | start Prometheus/Grafana/Loki/Tempo |

### 6.3 Port collisions & the optional override

On hosts where `5432` / `6379` are already occupied by another stack, an
optional `infrastructure/docker-compose.override.yml` remaps them to
`5433:5432` and `6380:6379`. If you create an override, you must either create
its external network first or drop the network block:

```bash
docker network create ehos-local   # only if you keep the external network block
```

### 6.4 Health checks

Point a browser (or `curl`) at:

```text
http://localhost:8000/health
http://localhost:8000/healthz
http://localhost:8000/metrics     # Prometheus format
```

Each service also exposes `GET /health`, `/healthz`, `/metrics` on its own port
and interactive OpenAPI docs at `http://localhost:<port>/docs`.

### 6.5 Optional monitoring stack

```bash
docker compose --profile monitoring up -d
```

| Tool | URL | Credentials |
|---|---|---|
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3000 | `admin` / `GRAFANA_ADMIN_PASSWORD` |
| Loki | http://localhost:3100 | — |
| Tempo | http://localhost:3200 | — |

---

## 7. Run path B — bare-metal / developer setup

Use this when iterating on one service with hot reload while the
infrastructure runs in containers.

### 7.1 Infrastructure only

```bash
docker compose up -d postgres redis kafka minio keycloak
```

> This machine's override remaps host ports to `5433` / `6380` — set
> `POSTGRES_PORT` and `REDIS_PORT` accordingly if an override is active.

### 7.2 Create the databases

```bash
python -m venv scripts/.venv
scripts/.venv/Scripts/pip install psycopg2-binary        # Windows
# scripts/.venv/bin/pip install psycopg2-binary          # Linux/macOS

python scripts/create_databases.py \
  --host localhost --port 5432 --user ehos --password <POSTGRES_PASSWORD>
```

This idempotently creates **all 28 `ehos_*` databases** (per-service DBs plus
`ehos_ai`, `ehos_analytics`, `ehos_knowledge`, `ehos_keycloak`, …). See
`scripts/create_databases.py` and `database/apply.py`.

Apply schema migrations (shared roles/extensions first, then each database):

```bash
python database/apply.py
```

### 7.3 Install the shared library (once per venv)

```bash
python -m venv .venv
source .venv/bin/activate                    # Windows: .venv\Scripts\activate
pip install -e shared/ehos-common
```

### 7.4 Install and run a single service

```bash
cd backend/<service>
pip install -e .
uvicorn <svc>_service.main:app --host 0.0.0.0 --port <port> --reload
```

Worked example — the laboratory service on `:8512`:

```bash
cd backend/laboratory-service
pip install -e .
uvicorn laboratory_service.main:app --host 0.0.0.0 --port 8512 --reload
```

Environment variables are read from `.env` in the current directory and the
shell (the shared keys in §5). The service is ready when
`http://localhost:<port>/docs` renders.

> Services without Alembic migrations create their tables automatically at
> startup (`init_models`) — the documented development path. Production must use
> the SQL migrations in `database/<service>_db/`.

### 7.5 Frontend apps

```bash
cd frontend/apps/ehr-portal                  # or patient-registration / ai-assistant / executive-dashboard
npm install
npm run dev     # serves on 5173–5176; proxies /api to the correct backend
```

`vite.config.ts` in each app maps short prefixes to their backend ports
(e.g. `/lab` → `:8512`, `/mpi` → `:8501`) or to the gateway. Production build:

```bash
npm run build
```

---

## 8. Service, port and gateway reference

### 8.1 Application services

| Port | Service | Purpose | API base |
|---|---|---|---|
| 8000 | api-gateway | routing, JWT, rate limit | `/api/v1/*` |
| 8100 | configuration | feature flags, config entries | `/api/v1/flags`, `/entries`, `/all` |
| 8200 | audit | immutable hash-chained audit records | `/api/v1/records`, `/integrity` |
| 8300 | notification | templates + delivery (log/smtp/http) | `/api/v1/templates`, `/send` |
| 8400 | Keycloak | identity, OIDC, realm `ehos` | `/realms/ehos`, `/admin` |
| 8500 | authentication | register/login, MFA, sessions, RBAC | `/api/v1/auth` |
| 8501 | patient (MPI) | demographics, merge, alerts | `/api/v1/patients` |
| 8502 | ehr | clinical record, notes, vitals, orders | `/api/v1/ehr` |
| 8503 | appointment | book/reschedule/cancel/availability | `/api/v1/appointments` |
| 8504 | queue | queues, tickets, advance | `/api/v1/queues` |
| 8505 | knowledge | RAG corpora, ingest, search, embed | `/api/v1/knowledge` |
| 8506 | ai | chat, agents, models, STT/TTS/OCR | `/api/v1/ai` |
| 8507 | prediction | train/approve/generate/reconcile | `/api/v1/predictions` |
| 8508 | analytics | warehouse metrics, dashboards | `/api/v1/analytics` |
| 8509 | billing | charges, invoices, payments | `/api/v1/billing` |
| 8510 | prescription | prescribing, MAR, allergies | `/api/v1/prescriptions` |
| 8511 | pharmacy | catalog, stock, dispensing | `/api/v1/pharmacy` |
| 8512 | laboratory | tests, orders, samples, results | `/api/v1/laboratory` |
| 8513 | radiology | modalities, orders, studies, reports | `/api/v1/radiology` |
| 8514 | inventory | items, stock, movements, alerts | `/api/v1/inventory` |
| 8515 | workflow | definitions, instances, transitions | `/api/v1/workflows` |
| 8516 | clinical-documentation | notes, versions, templates | `/api/v1/documentation` |
| 8517 | insurance | coverages, claims, prior auths | `/api/v1/insurance` |
| 8518 | reporting | definitions, instances, schedules | `/api/v1/reporting` |

Gateway routing is declared in
`backend/api-gateway/src/api_gateway/routing/routes.py`. The gateway also
rewrites the frontend short prefixes — `/mpi`, `/sched`, `/q`, `/bill`, `/rx`,
`/pharm`, `/lab`, `/rad`, `/inv`, `/wf`, `/doc`, `/ins`, `/rpt` — to the
canonical `/api/v1/*` path of the correct upstream.

### 8.2 Databases (all `database/<svc>_db/V001__init.sql`)

`ehos_ai`, `ehos_analytics`, `ehos_audit`, `ehos_bed`, `ehos_billing`,
`ehos_configuration`, `ehos_documentation`, `ehos_ehr`, `ehos_emergency`,
`ehos_finance`, `ehos_hr`, `ehos_identity`, `ehos_insurance`, `ehos_inventory`,
`ehos_knowledge`, `ehos_laboratory`, `ehos_notification`, `ehos_patient`,
`ehos_payroll`, `ehos_pharmacy`, `ehos_prescription`, `ehos_procurement`,
`ehos_radiology`, `ehos_reporting`, `ehos_scheduling`, `ehos_surgery`,
`ehos_telemedicine`, `ehos_workflow` plus `ehos_keycloak`.
Shared roles/extensions live in `database/shared/`.

---

## 9. Keycloak identity (for the gateway and AI)

- Realm `ehos`, imported automatically at first start from
  `backend/identity-service/keycloak/realm-ehos.json`.
- Admin console: http://localhost:8400/admin — `admin` /
  `KEYCLOAK_ADMIN_PASSWORD` (dev default `Ehos-Admin-2026`).
- Dev admin user `admin` in the master and `ehos` realms.

Obtain a token for gateway-protected routes:

```bash
curl -s -X POST http://localhost:8400/realms/ehos/protocol/openid-connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" -d "client_id=ehos-api" \
  -d "client_secret=<KEYCLOAK_CLIENT_SECRET>" \
  -d "username=admin" -d "password=<KEYCLOAK_ADMIN_PASSWORD>" -d "scope=openid"
```

Use the returned `access_token` as
`Authorization: Bearer <access_token>` on every gateway call.

---

## 10. Two identity paths — read before deployment

1. `authentication-service` (`:8500`) issues **its own RS256 JWTs**
   (configurable `JWT_PRIVATE_KEY_PEM`/`JWT_PUBLIC_KEY_PEM`; ephemeral in dev).
2. `api-gateway` and `ai-service` validate **every** JWT against **Keycloak's
   JWKS** and fail closed (401) on unknown tokens.

**Consequence:** tokens minted by `authentication-service` are currently
rejected by the gateway/AI (different signer), and direct service calls do not
need a token in dev (except `ai-service`). Reconcile before production — the
preferred fix is to issue all tokens through the Keycloak realm (OIDC
client-credentials or token exchange) so a single JWKS covers everything. See
`INSTALLATION_AND_USAGE.md` §9 for the full analysis and options.

---

## 11. Testing, linting and schema migration

```bash
make test          # pytest across all 22 backend services + gateway
make lint          # ruff check across all services + shared/ehos-common
make migrate       # python database/apply.py
```

Per package (any OS):

```bash
cd shared/ehos-common && python -m pytest -q && python -m ruff check src tests
cd backend/<service> && python -m pytest -q && python -m ruff check src tests
```

Windows helper for the full Phase-0 suite:

```powershell
powershell -File scripts/run_tests.ps1
```

Frontend checks: `npm run typecheck` and `npm run build` inside each app.

---

## 12. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `docker compose up` fails on "network ehos-local declared as external" | an override is present — `docker network create ehos-local` or remove the network block from the override |
| Container exits with `POSTGRES_PASSWORD must be set` | `EHOS_ENV` is not `development` and the default password is still set — set a real password in `.env` |
| 401 from gateway / ai-service | you need a **Keycloak** token (§9), not an `authentication-service` token; refresh on expiry (15 min default) |
| `RUNTIME_UNAVAILABLE` / 404 in AI status | the configured Ollama model is not installed — use an installed model or `INFERENCE_ADAPTER=mock` |
| Knowledge-embedding errors | `EMBEDDING_ADAPTER=ollama` needs an embedding model (e.g. `all-minilm:l6-v2`); completion-only models cannot embed |
| Service does not start; check `/docs` blank | DB not created — run `scripts/create_databases.py` then `database/apply.py` (§7.2) |
| `500` errors with a short code | inspect `docker compose logs <service>`; handlers return the envelope `{"success","data","timestamp"}` with `errorCode`/`message` |
| Port already in use | stop the conflicting process or remap the port (override / env `*_PORT`) |
| HTTP 503 on backend unavailable in the UI | the upstream service is down — start it and reload the page |

---

## 13. Where to go next

- `USER_GUIDE.md` — plain-language guide to every module and process.
- `INSTALLATION_AND_USAGE.md` — every configuration option per service.
- `README.md` — quick start + standards pointers.
- `CHANGELOG.md` — current build state and version history.
- Architecture documents (`EHOS_ARCHITECTURE_DESIGN.md`, `DATABASE_DESIGN.md`,
  `HOSPITALGPT_ARCHITECTURE.md`, `SECURITY_AND_COMPLIANCE_ARCHITECT.md`, …).