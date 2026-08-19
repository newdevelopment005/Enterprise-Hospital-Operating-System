# EHOS — Installation & Usage Guide

Everything you need to install, configure, and use every option of the EHOS
(Enterprise Hospital Operating System) monorepo. The build is **Phase 0:
Foundation Platform** plus the offline AI (HospitalGPT) stack (see
`CHANGELOG.md`).

> Two supported ways to run the stack:
> **Option A — Docker Compose** (recommended, one command, includes
> infrastructure) and **Option B — bare-metal / local development** (venv +
> `uvicorn`, needs PostgreSQL/Kafka/Redis running on the host).

---

## 1. Prerequisites

| Requirement | Version | Used by |
|---|---|---|
| Docker + Docker Compose v2 | any recent | Option A |
| Python + pip + `venv` | 3.11+ (3.13 tested) | Option B |
| `make` | any | Linux/macOS/WSL convenience targets |
| PowerShell | 5.1+ | Windows test helper `scripts/run_tests.ps1` |
| psycopg2 (Python package) | latest | `scripts/create_databases.py` |

Required UDP/TCP ports (Option B / infra containers):

| Port | Service |
|---|---|
| 5432 | PostgreSQL |
| 6379 | Redis |
| 9092 | Kafka |
| 9000 / 9001 | MinIO (API / console) |
| 8400 | Keycloak (published; container listens on 8080) |
| 8000 | api-gateway |
| 8100 / 8200 / 8300 | configuration / audit / notification |
| 8500 | authentication |
| 8501 / 8502 | patient / ehr |
| 8505 / 8506 / 8507 | knowledge / ai / prediction |
| 9090 / 3000 / 3100 / 3200 | monitoring profile (prometheus/grafana/loki/tempo) |

---

## 2. Option A — Full stack with Docker Compose

### 2.1 One-time setup

```bash
make init          # copy .env.example -> .env, create data/minio + data/postgres
make build         # build all service images (fastest on first run)
```

`make init` never overwrites an existing `.env`. Open `.env` and replace every
`change-me` value before going past a laptop.

### 2.2 Start / stop

```bash
make up            # start everything in the background
make ps            # verify all containers are healthy
make logs          # tail all service logs (ctrl-c to stop)
make kafka-topics  # list the Kafka topics created on the bus
make down          # stop the stack (volumes are kept)
```

Health endpoints: `http://localhost:8000/health`, `/healthz`, `/metrics`
(these are deliberately excluded from auth/rate-limiting).

### 2.3 Start only the infrastructure

```bash
docker compose up -d postgres redis kafka minio keycloak
```

Useful when you want to run the Python services locally (Option B) against the
containerised infrastructure.

### 2.4 Optional monitoring stack (Prometheus / Grafana / Loki / Tempo)

```bash
docker compose --profile monitoring up -d
```

| Tool | URL |
|---|---|
| Prometheus | http://localhost:9090 |
| Grafana (admin / password from `GRAFANA_ADMIN_PASSWORD`, default `admin`) | http://localhost:3000 |
| Loki | http://localhost:3100 |
| Tempo | http://localhost:3200 |

---

## 3. Option B — Bare-metal / local development

### 3.1 Create the databases

The `infrastructure/database/init/001_create_databases.sql` (mounted by the
Postgres container) creates only five dev databases. For local dev create the
full set (idempotent):

```bash
python -m venv scripts/.venv        # or reuse any venv
scripts/.venv/Scripts/pip install psycopg2-binary
python scripts/create_databases.py \
  --host localhost --port 5432 --user ehos --password <POSTGRES_PASSWORD>
```

This creates every database incl. `ehos_identity`, `ehos_patient`, `ehos_ehr`,
`ehos_knowledge`, `ehos_ai`. Services that ship Alembic migrations
(`authentication-service`, `configuration-service`, `patient-service`) can also
run them: `alembic upgrade head` from the service directory. Non-migrated
services create their tables automatically at startup (`init_models`), which is
the documented **development** path — production must use migrations.

### 3.2 Install `ehos-common` (editable)

Every service depends on `ehos-common==0.1.0`. Install it once, editably, into
your venv:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e shared/ehos-common
```

### 3.3 Install and run a service

For each service you want to run:

```bash
cd backend/<service>
pip install -e .
uvicorn <module>:app --host 0.0.0.0 --port <port> --reload
```

One service, worked example (`notification-service`, port 8300):

```bash
cd backend/notification-service
pip install -e .
uvicorn notification_service.main:app --host 0.0.0.0 --port 8300 --reload
```

Environment variables are read from `.env` in the current directory and from
the shell. Simplest workflow: `export` the shared vars once (see §5.1) or place
a `.env` file next to each service.

The **no-op treadmill check**: each service health-checks itself by opening its
own `/docs` before reporting healthy — the service is usable when
`http://localhost:<port>/docs` renders the OpenAPI Swagger UI.

---

## 4. Service inventory & routing

All services are FastAPI. The gateway (`:8000`) is the single entry point and
rewrites path prefixes to the correct upstream:

| Prefix | Upstream service | Port | Requires auth | Role |
|---|---|---|---|---|
| `/api/v1/auth` | authentication-service | 8500 | no (service self-protects) | — |
| `/api/v1/patients` | patient-service | 8501 | yes | — |
| `/api/v1/ehr` | ehr-service | 8502 | yes | — |
| `/api/v1/knowledge` | knowledge-service | 8505 | yes | — |
| `/api/v1/ai` | ai-service | 8506 | yes | — |
| `/api/v1/predictions` | prediction-service | 8507 | yes | — |
| `/api/v1/records`, `/api/v1/integrity` | audit-service | 8200 | yes | — |
| `/api/v1/flags`, `/api/v1/entries` | configuration-service | 8100 | yes | administrator |
| `/api/v1/templates`, `/api/v1/send` | notification-service | 8300 | yes | — |

A client may also hit any service directly at its own port. OpenAPI docs are
always at `http://localhost:<port>/docs` (openapi spec at
`/api/v1/openapi.json`).

---

## 5. Every configuration option

### 5.0 How options are read

- Pydantic `BaseSettings`; env var name = upper-case field name, case
  insensitive. E.g. service field `jwt_access_ttl_seconds` = `JWT_ACCESS_TTL_SECONDS`.
- Shared fields carry explicit `EHOS_` etc. aliases (table below).
- Unknown vars are ignored (`extra="ignore"`).
- `EHOS_ENV` must be `development` to use the default `POSTGRES_PASSWORD=ehos`;
  any other value fails fast until a real password is set.

### 5.1 Shared — every service (`ehos-common`)

| Option | Default | Purpose |
|---|---|---|
| `EHOS_ENV` | `development` | Runtime environment; fails fast on default DB password when not `development` |
| `EHOS_LOG_LEVEL` | `INFO` | structlog level |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka cluster for events/outbox |
| `POSTGRES_HOST` / `POSTGRES_PORT` | `localhost` / `5432` | PostgreSQL addressing |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | `ehos` / `ehos` | DB credentials (set a real one outside dev) |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` | `localhost` / `6379` / empty | Redis (rate limit, caching, idempotency) |
| `KEYCLOAK_URL` | `http://localhost:8080` | Keycloak base URL for JWKS validation |
| `KEYCLOAK_REALM` | `ehos` | Realm whose JWKS is trusted |

> Note: the API gateway (and `ai-service`) validate JWTs against
> `KEYCLOAK_URL/realms/KEYCLOAK_REALM/.../certs`. In the published dev stack
> Keycloak is reachable at **http://localhost:8400** — set `KEYCLOAK_URL`
> accordingly when the services talk to it from the host (containers use
> `http://keycloak:8080`).
> Never point a service at a production cluster with `POSTGRES_PASSWORD=ehos`.

### 5.2 api-gateway (port 8000)

Options are only the shared set (§5.1) plus two built-in behaviours you can
expect, not configure:

- **Auth bypass paths** (hard-coded): `/health`, `/healthz`, `/metrics`,
  `/docs`, `/openapi.json`, `/api/v1/openapi.json`.
- **Header forwarding**: only hop-by-hop-safe upstream headers are passed
  through (`content-type`, `content-disposition`, `set-cookie`,
  `www-authenticate`, `location`, `cache-control`, `etag`, `retry-after`) plus
  the correlation `X-Request-Id`; all others are dropped.
- **Rate limiting / Redis**: blocking lookups are off the event loop and the
  gateway **fails open** (logs + continues) when Redis is unreachable.

Routing table is `backend/api-gateway/src/api_gateway/routing/routes.py`.

### 5.3 authentication-service (port 8500)

Self-service registration, login, TOTP MFA, sessions, lockout, JWT issuance.

| Option | Default | Purpose |
|---|---|---|
| `JWT_ALGORITHM` | `RS256` | Asymmetric signing in all environments |
| `JWT_ACCESS_TTL_SECONDS` | `900` | Access-token lifetime (15 min) |
| `JWT_REFRESH_TTL_SECONDS` | `2592000` | Refresh-token lifetime (30 days) |
| `JWT_ISSUER` | `http://localhost:8500` | `iss` claim |
| `JWT_AUDIENCE` | `ehos-api` | `aud` claim |
| `JWT_PRIVATE_KEY_PEM` / `JWT_PUBLIC_KEY_PEM` | unset | Signing/verification keypair. When unset an **ephemeral** key is generated at startup (dev only) |
| `REGISTER_DEFAULT_ROLE` | `user` | Role granted at self-service sign-up (privileged roles are admin-granted only) |
| `MFA_ENCRYPTION_KEY` | unset | Fernet key for encrypting TOTP secrets; when unset, derived from the JWT private key (refused outside dev) |
| `SESSION_IDLE_TTL_SECONDS` | `43200` | Idle session timeout (12 h) |
| `MAX_SESSIONS_PER_USER` | `5` | Concurrent session cap |
| `MFA_ISSUER` / `MFA_WINDOW` / `MFA_CHALLENGE_TTL_SECONDS` | `EHOS` / `1` / `120` | TOTP identity, clock-skew allowance (±1 step), challenge lifetime |
| `PASSWORD_MIN_LENGTH` | `12` | Minimum password length |
| `PASSWORD_REQUIRE_UPPER` / `_LOWER` / `_DIGIT` / `_SPECIAL` | `true` | Character-class requirements |
| `PASSWORD_HISTORY_SIZE` | `5` | Cannot reuse the last N passwords |
| `PASSWORD_MAX_AGE_DAYS` | `90` | Forced rotation interval |
| `LOGIN_FAILURE_LIMIT` | `5` | Failed attempts before lockout |
| `LOCKOUT_MINUTES` | `15` | Lockout duration |

Auth events are emitted on `auth.topic` (e.g. `UserAuthenticated`,
`PasswordChanged`) for the audit-service to mirror.

### 5.4 patient-service (MPI, port 8501)

| Option | Default | Purpose |
|---|---|---|
| `MRN_PREFIX` | `EH` | MRN generator prefix (`EH000001`) |
| `PATIENT_NUMBER_PREFIX` | `P` | Patient-number generator prefix |
| `NUMBER_WIDTH` | `6` | Zero-padded width of generated ids |
| `DEFAULT_COUNTRY` | `TZ` | Default country on registration |
| `SEARCH_LIMIT` / `SEARCH_MAX_LIMIT` | `50` / `200` | Search pagination cap |

Publishes on canonical topics: `clinical.patient.registered`,
`clinical.patient.updated`, `clinical.patient.merged`,
`clinical.patient.deactivated`.

### 5.5 ehr-service (clinical record, port 8502)

| Option | Default | Purpose |
|---|---|---|
| `SEARCH_LIMIT` / `SEARCH_MAX_LIMIT` | `50` / `200` | Pagination caps |
| `DEFAULT_LANGUAGE` | `en` | Default note language |
| `MAX_NOTE_CONTENT` | `100000` | Max chars per note |
| `MAX_HISTORY_ENTRIES` / `MAX_TIMELINE_ENTRIES` | `500` / `1000` | Redact/rollup limits for history/timeline |

Emits `clinical.ehr.record.updated` when records change.

### 5.6 knowledge-service (RAG, port 8505)

| Option | Default | Purpose |
|---|---|---|
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `800` / `120` | Ingestion chunking |
| `EMBEDDING_ADAPTER` | `mock` | `mock` or `ollama` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `EMBEDDING_MODEL` / `EMBEDDING_DIM` | `nomic-embed-text` / `384` | Embedding model + vector width |
| `SEARCH_TOP_K` / `SEARCH_MAX_TOP_K` | `8` / `25` | Retrieval candidates |
| `SIMILARITY_THRESHOLD` | `0.1` | Min similarity to return a hit |
| `MAX_UPLOAD_BYTES` | `20000000` | Max upload size (20 MB) |
| `PDF_MAX_PAGES` / `MAX_DOCUMENTS_PER_FILE` | `500` / `2000` | Ingestion caps |

Bootstraps the four offline medical corpora on startup (idempotent). Emits
`knowledge.document.ingested`.

### 5.7 ai-service (HospitalGPT, port 8506)

#### Inference & embeddings

| Option | Default | Purpose |
|---|---|---|
| `INFERENCE_ADAPTER` | `mock` | `mock` • `ollama` • `llamacpp` • `openai` |
| `EMBEDDING_ADAPTER` | `mock` | `mock` or `ollama` |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | `http://localhost:11434` / `llama3.1` | Ollama runtime binding |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Ollama embedder |
| `LLAMACPP_BASE_URL` | `http://localhost:8080` | llama.cpp server endpoint |
| `OPENAI_BASE_URL` | `http://localhost:8000/v1` | Any OpenAI-compatible server (vLLM, LM Studio, Ollama, OpenAI) |
| `OPENAI_API_KEY` | unset | Optional key for the OpenAI-compatible endpoint |
| `OPENAI_MODEL` | `ehos-gpt` | Model name sent to the compatible server |

> Heads-up: the Docker Compose snippet sets `AI_INFERENCE_ADAPTER` /
> `AI_EMBEDDING_ADAPTER`, but the settings loader reads bare
> `INFERENCE_ADAPTER` / `EMBEDDING_ADAPTER` (others are ignored with
> `extra="ignore"`). The `mock` default is identical either way, so the dev
> stack behaves the same — use the bare names above for real configuration.

#### RAG bridge

| Option | Default | Purpose |
|---|---|---|
| `KNOWLEDGE_SERVICE_URL` | `http://localhost:8505` | RAG upstream |
| `KNOWLEDGE_TIMEOUT` | `20.0` | RAG call timeout (s) |
| `RAG_TOP_K` | `5` | Context chunks injected per prompt |

#### Prompt / model manager

| Option | Default | Purpose |
|---|---|---|
| `DEFAULT_MODEL_KEY` | `llama-3.1-8b` | Default model registry key |
| `DEFAULT_SYSTEM_PROMPT_CODE` | `hospitalgpt_system` | Default system prompt key |
| `MAX_CONTEXT_WINDOWS` | `24` | Rolling-context window cap |

#### Media facades (STT / TTS / OCR)

| Option | Default | Purpose |
|---|---|---|
| `STT_ADAPTER` / `TTS_ADAPTER` / `OCR_ADAPTER` | `mock` | `mock` or `http` |
| `STT_HTTP_URL` / `STT_HTTP_TOKEN` | unset | Speech-to-text HTTP endpoint (+ bearer token) |
| `TTS_HTTP_URL` / `TTS_HTTP_TOKEN` | unset | Text-to-speech HTTP endpoint (+ bearer token) |
| `OCR_HTTP_URL` / `OCR_HTTP_TOKEN` | unset | OCR HTTP endpoint (+ bearer token) |
| `MEDIA_TIMEOUT` | `60.0` | Media facade timeout (s) |

#### Security

Endpoints **re-validate the caller's JWT against Keycloak JWKS on every
request** (`KEYCLOAK_URL`/`KEYCLOAK_REALM`, §5.1). When Keycloak is down the
service **fails closed (401)**. Conversation/memory/agent identity comes from
the token subject — client-supplied `user_id`/`approver_id` are ignored.

### 5.8 prediction-service (offline forecasting, port 8507)

| Option | Default | Purpose |
|---|---|---|
| `DEFAULT_ADAPTER` | `seasonal_naive` | Forecast family (seasonal-naive / SES). Compose sets `PREDICTION_DEFAULT_ADAPTER`, which the loader ignores (`extra="ignore"`) — the default is identical |
| `DEFAULT_PERIOD` | `7` | Seasonality period |
| `DEFAULT_HORIZON_STEPS` | `7` | Forecast horizon |
| `DEFAULT_CONFIDENCE` | `0.90` | Prediction interval |
| `EVENT_SOURCE` | `prediction-service` | Source for the emitted `ai.prediction.generated` event |

All forecasting is local and offline (single-node; advisory only).

### 5.9 audit-service (port 8200)

Options are the shared set (§5.1) plus fixed guarantees:

- Consumes `auth.topic`, `audit.topic` and every registry topic; poisons
  (non-JSON) are logged and skipped; broker errors are retried with backoff.
- Records are written to the tamper-evident hash chain; `verify_chain` catches
  tampering. Malformed chain → `INVALID_CHAIN` on `/api/v1/integrity`.

### 5.10 configuration-service (port 8100)

Shared options only (§5.1). Feature flags + reference configuration, emits
`configuration.topic` / `ConfigurationUpdated` on change. All
`/api/v1/flags` and `/api/v1/entries` routes require the `administrator` role.

### 5.11 notification-service (port 8300)

The delivery transport is opt-in:

| Option | Default | Purpose |
|---|---|---|
| `NOTIFICATIONS_TRANSPORT` | `log` | `log` • `smtp` • `http` |
| `ADMISSION_INBOX` | `admissions@ehos.example` | Fallback recipient when a payload carries no contact channel |

- **`log`** (default): adapters log the delivery and return a deterministic
  mock id — no external credentials, safe for dev.
- **`smtp`**: `EmailAdapter` sends via a real SMTP relay. `SmsAdapter` /
  `PushAdapter` still log.
- **`http`**: `SmsAdapter` / `PushAdapter` POST to provider webhooks
  (`SMS_HTTP_URL`/`SMS_HTTP_TOKEN`, `PUSH_HTTP_URL`/`PUSH_HTTP_TOKEN`);
  `EmailAdapter` falls back to SMTP settings.

SMTP options: `SMTP_HOST` (`localhost`), `SMTP_PORT` (`25`),
`SMTP_USERNAME`/`SMTP_PASSWORD` (unset), `SMTP_USE_TLS` (`true`),
`SMTP_FROM` (`noreply@ehos.example`), `SMTP_TIMEOUT` (`10.0`).

---

## 6. Testing & linting

```bash
# Everything (Linux/macOS/WSL)
make test
make lint
make migrate

# Windows PowerShell helper (Phase 0 services)
powershell -File scripts/run_tests.ps1
```

Per package (any OS):

```bash
cd shared/ehos-common && python -m pytest -q && python -m ruff check src tests
cd backend/<service> && python -m pytest -q && python -m ruff check src tests
```

Full suite status: **240 tests passing**, every package ruff-clean
(shared 63, ai 34, api-gateway 9, audit 5, authentication 15, configuration 3,
ehr 26, knowledge 33, notification 17, patient 18, prediction 17).

---

## 7. Event bus reference

Kafka auto-creates topics (`AUTO_CREATE_TOPICS_ENABLE=true`). Envelope,
naming and schema conventions live in `EVENT_BUS.md` /
`EVENT_BUS_SCHEMAS.md`. The single source of truth is
`shared/ehos-common/src/ehos_common/event_registry.py`.

| EventType | Topic | Source |
|---|---|---|
| `PatientRegistered` | `clinical.patient.registered` | patient-service |
| `PatientUpdated` | `clinical.patient.updated` | patient-service |
| `PatientMerged` | `clinical.patient.merged` | patient-service |
| `PatientDeactivated` | `clinical.patient.deactivated` | patient-service |
| `ConfigurationUpdated` | `configuration.topic` | configuration-service |
| `ClinicalRecordUpdated` | `clinical.ehr.record.updated` | ehr-service |
| `KnowledgeDocumentIngested` | `knowledge.document.ingested` | knowledge-service |
| `AIRequestCreated` | `ai.request.created` | ai-service |
| `AIResponseGenerated` | `ai.response.generated` | ai-service |
| `PredictionGenerated` | `ai.prediction.generated` | prediction-service |
| `AppointmentCreated`, `LabOrdered`, `MedicationDispensed`, `EmergencyTriggered`, `InventoryUpdated`, `BillGenerated`, `PayrollCompleted` | `clinical.*` / `supply.*` / `finance.*` / `hr.*` | yet-to-be-built services (schema-locked) |

`auth.topic` carries auth-security events (login, password change,
token-reuse). `audit.topic` is the audit mirroring basis.

---

## 8. Every-day workflow summary

```bash
make init && make build && make up    # one-time
make ps                                # is everything healthy?
make logs                              # watch the platform
make kafka-topics                      # inspect the bus
make test && make lint                 # verify changes
docker compose --profile monitoring up -d   # metrics/logs/traces dashboards
make down                              # stop (keeps volumes)
```

---

## 9. Architectural note — two identity paths (read this)

EHOS currently has **two independent identity/signing paths that do not
interoperate**:

1. **`authentication-service` (the in-repo IAM)** issues its own RS256 JWTs,
   signed with `JWT_PRIVATE_KEY_PEM`/`JWT_PUBLIC_KEY_PEM` (issuer default
   `http://localhost:8500`, audience `ehos-api`), and keeps its own
   sessions, TOTP MFA, password policy and lockout state (§5.3).
2. **`api-gateway` and `ai-service`** validate *every* incoming JWT against
   **Keycloak's JWKS** (`KEYCLOAK_URL`/`KEYCLOAK_REALM`
   → `/realms/{realm}/protocol/openid-connect/certs`, §5.1). The `ai-service`
   now fails closed (401) on any invalid/unknown token. Keycloak itself is
   provided by `identity-service` (realm `ehos`) and imports users/clients at
   startup.

**Consequence:** a token issued by `authentication-service` is signed by a key
that is *not* in Keycloak's JWKS, so the gateway and `ai-service` **reject the
service's own tokens with 401**. Conversely, Keycloak-issued tokens are not
recognised by `authentication-service`'s verifier (it only trusts its own
public key). The gap is currently masked only because the `/api/v1/auth` route
is public (`requires_auth: false`) and routes like `/api/v1/ai` were only
recently wired to JWKS validation. Any real deployment must reconcile the two
before tokens can guard the `/api/v1/ai`, `/api/v1/knowledge`,
`/api/v1/predictions`, `/api/v1/patients`, `/api/v1/ehr` and
`/api/v1/records` routes end-to-end.

**Recommended resolution (pick one, in order of preference):**

1. **Single signer — Keycloak issues all tokens (recommended).** Make
   `authentication-service` issue tokens *through* the Keycloak realm — use the
   OIDC client-credentials flow or a token-exchange between the service's
   client and the realm so the returned JWT carries Keycloak's issuer, audience
   and signing key. Then the gateway/`ai-service` JWKS validation works
   unchanged for every token, and users get SSO/MFA from Keycloak while
   `authentication-service` provides the EHOS-specific enrolment, self-service
   and lockout policy.
2. **Expose `authentication-service`'s public key as an additional JWKS** (a
   `.well-known/jwks.json` served by the service, then taught to the gateway's
   trusted set next to Keycloak's). Keeps two signers — acceptable, but must
   keep key rotation and CORS/identity in sync, and it retains the split
   identity model.
3. **De-scope Keycloak to external SSO only; use `authentication-service` as
   the internal IAM.** The gateway and `ai-service` would then validate against
   `authentication-service`'s JWKS instead of Keycloak's, per-service key
   retrieval stays internal, and Keycloak is used solely for patient/provider
   SSO/federation. Larger change to the gateway + `ai-service` for negligible
   benefit if option 1 is viable.

**Concrete alignment steps for option 1 (what "done" looks like):**

- Set `JWT_ISSUER` to the realm issuer
  (`http://localhost:8400/realms/ehos` when published on the host),
  `JWT_AUDIENCE` to the `ehos-api` client's audience, and stop using
  `JWT_PRIVATE_KEY_PEM`/`JWT_PUBLIC_KEY_PEM` (persist nothing; issue via
  Keycloak).
- Ensure `KEYCLOAK_URL` reached by every service resolves to the same public
  Keycloak hostname (`http://localhost:8400` from the host /
  `http://keycloak:8080` in Compose).
- Remove `requires_auth: false` for `/api/v1/auth` once the service stops
  self-issuing tokens, and add role checks (`administrator` etc.) everywhere
  the DTOs currently rely on client-supplied `user_id`/`approver_id`.
- Add a test that a Keycloak-issued token passes gateway + `ai-service`
  validation **and** is honoured by `authentication-service` internals; set
  `EHOS_ENV`/lockout and MFA values before cutover so lockout keys survive the
  move.

Until this is done, treat gate-checked routes as **single-signer pending**: any
token accepted at `/api/v1/*` today must come from Keycloak, and
`authentication-service`'s own tokens are for direct (bypassing the gateway)
use only.