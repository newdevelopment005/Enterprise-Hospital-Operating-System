# Changelog

All notable changes to EHOS (Enterprise Hospital Operating System) are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/).

## [0.4.4] - 2026-08-19

### Deep audit — crash-path, security and event-integrity hardening

- **Response-envelope 500s fixed** (`response_model` removed): every handler in
  authentication/patient/audit/configuration/notification services returned the
  success envelope `{"success", "data", "timestamp"}`, but decorated with
  `response_model=SomeOut`, so FastAPI serialized the envelope against the DTO —
  a guaranteed 500 on every call. All 45 decorators stripped; response schemas
  remain available for documentation/tests. Files re-encoded to plain UTF-8.
- **Auth-service security state persisted on error responses**: `get_session`
  committed only on success, so failed-login counters, lockouts, expired-token
  flags and refresh-token family revocations were rolled back whenever a handler
  answered 401/423. The dependency now commits pending security state before
  re-raising (no-op rollback when nothing changed), making brute-force lockout
  and token-reuse detection actually take effect. Refresh-token replay now
  revokes the whole token family (`TOKEN_REUSE_DETECTED`); session revocation
  verifies ownership so one user can no longer revoke another's session.
- **AI-service zero-trust**: `AuthDeps` was never wired — all endpoints were
  unauthenticated. Every data endpoint now re-validates the caller's bearer JWT
  against cached JWKS (fail-closed 401 when Keycloak is down); client-supplied
  `user_id`/`approver_id` are ignored in favour of the token subject, and
  conversations/memories are scoped to the caller.
- **Gateway fixes**: query strings were dropped when proxying (now preserved);
  upstream `content-type`/`location`/`set-cookie`/`www-authenticate` headers are
  forwarded (hop-by-hop excluded) so JSON/media/auth responses stay intact;
  `/health`, `/metrics`, `/docs` are exempt from auth/rate-limit (previously
  404); the blocking Redis rate-limit call moved off the event loop and now
  fails open with a warning when Redis is down instead of 500ing.
- **Patient eventing aligned with the schema registry**: patient-service
  published `PatientRegistered`/`PatientUpdated`/`PatientMerged`/
  `PatientDeactivated` to non-canonical `patient.topic`. The three missing event
  types are now registered (schemas + catalog) and the service publishes to the
  canonical `clinical.patient.*` topics; audit/notification consumers derive
  subscriptions from the registry instead of hardcoded topics.
- **Publish-after-commit (in-memory outbox)**: patient/knowledge/prediction
  published before the DB commit, so a failed commit emitted phantom events. A
  per-request `ehos_common.Outbox` is wired into each `get_session` dependency:
  events are staged on `session.info["outbox"]` and flushed only after commit,
  discarded on rollback.
- **Audit consumer resilience**: a malformed message (non-JSON) previously
  crashed the whole consumer loop via the shared deserializer; `getmany`
  failures killed it too. Messages are now parsed per-record (poison pills
  logged and skipped) and transient broker errors are retried with backoff.
- **Audit hash-chain fixes**: `compute_hash` canonicalized naive datetimes
  (sqlite round-trips otherwise flagged a valid chain as tampered); the
  chain-tail read now uses `FOR UPDATE` so concurrent writers cannot fork the
  chain.
- **AI adapters**: OpenAI-compatible non-JSON responses now surface `502`
  `RUNTIME_BAD_RESPONSE` instead of a 500; a missing `content` field yields an
  empty result (no `KeyError`); the runtime ping sends the configured
  `Authorization` header for keyed endpoints.
- **PHI hygiene**: the duplicate-patient error no longer echoes the existing
  patient's MRN.
- **Tests**: 18 new regression tests (auth lockout/reuse/ownership through the
  dependency error path, gateway header/query behavior, outbox flush/discard,
  patient canonical-topic publication, audit consumer poison-pill + chain
  round-trip, AI adapter error paths). Full suite: 240 tests green, all services
  ruff-clean.

## [0.4.3] - 2026-08-18

### Dead placeholders replaced with working runtime adapters

- **Notification delivery transport** (`notification-service`): replaces the
  "log and succeed" stubs with `build_adapters(settings)` — real SMTP delivery
  via `smtplib` (AUTH/TLS from `NotificationSettings`), HTTP SMS/push providers
  through `httpx` with bearer auth, plus deterministic log-mode fallback.
  `NotificationSettings` gains `notifications_transport` (log/smtp/http) and
  per-channel credentials; adapters raise on failure so the service's
  `MAX_ATTEMPTS` retry loop actually retries.
- **Notification consumer fires on real events**: the old pipeline mapped
  `AppointmentCreated` on a topic no producer writes; it now wraps the shared
  `EventProcessor` (schema validation → retry ladder → DLQ), derives its
  subscriptions from the event registry (`registry.topics_for` + `patient.topic`),
  and routes the live `PatientRegistered` event to the configured admission
  inbox. Consumer accepts an injectable consumer for hermetically tested runs.
- **EHR producer un-dead-wired**: `EhrService` previously created a KafkaProducer
  it never used. It now accepts the producer and publishes `ClinicalRecordUpdated`
  to `clinical.ehr.record.updated` from every clinical-timeline write
  (encounters, notes, diagnoses, orders, ...) — best-effort so local dev without
  a bus still works. Optional payload fields (`recordId`, `recordType`, `actorId`)
  are omitted when absent so every envelope conforms to the registry schema;
  emitting `null` there would otherwise DLQ the event in validating consumers.
  New registry event type + `ehr.topic` mirrored by the audit consumer
  automatically.
- **Schema registry forward-compat**: payload schemas were `additionalProperties:
  false` while producers enrich payloads (e.g. patient-service adds
  `firstName`/`lastName`), which would have routed every real event to the DLQ.
  Envelope-level strictness is kept; payloads now allow forward-compatible
  extension. `PatientRegistered` producer payload also includes the required
  `registeredAt`.
- **AI adapters** (`ai-service`): inference now supports any OpenAI-compatible
  endpoint (`inference_adapter=openai` with base URL/optional key/model);
  STT/TTS/OCR facades no longer 503 for non-mock — they post to configured
  `stt_http_url`/`tts_http_url`/`ocr_http_url` endpoints (raw bytes, bearer
  auth) and return the provider transcription/audio/OCR text.
- **Tests**: new suites for notification adapters (log/smtp/http + failure
  paths), the event→notification pipeline (consume + DLQ on invalid events),
  EHR bus publishing (including registry-schema conformance for events without
  an entity or actor), and AI openai/media HTTP adapters. All suites remain
  ruff-clean and green: shared library 57 tests, services 165 tests (gateway 9,
  auth 13, ehr 26, patient 16, config 3, audit 2, notification 16, knowledge 33,
  prediction 17, ai 30).

## [0.4.2] - 2026-08-18

### Actual working runtime — idempotency, observability, auth, event mirroring

- **Idempotency keys** (`ehos_common.idempotency`): `POST`/`PUT`/`PATCH`
  requests carrying an `Idempotency-Key` header are fingerprinted (method+path+
  key+body, key-scoped so distinct keys never cross-replay) and answers are
  stored; a repeated request returns the original response with
  `x-ehos-idempotency-replay: true`, so client retries cannot create duplicate
  patients/notes/orders. Memory store for single-replica dev, Redis store for
  multi-replica prod; transparent when no key is sent. Middleware wired into
  all 10 service mains.
- **Observability** (`ehos_common.metrics`): dependency-free Prometheus
  exporter — counter/gauge/histogram registry plus an ASGI middleware recording
  request rate, latency and 5xx per route. Every service exposes
  `GET /metrics` (Prometheus text format) through the shared health router;
  Prometheus stack in `infrastructure/monitoring` can scrape it now.
- **Shared auth dependency** (`ehos_common.auth`): `build_auth_deps(settings)`
  exposes FastAPI dependencies (`current_user`, `require(...roles)`) that
  re-validate the forwarded bearer JWT against cached JWKS and enforce RBAC on
  data-plane endpoints — defense in depth behind the gateway.
- **Audit topic mirror fixed**: audit consumer previously subscribed only to
  `audit.topic`, which no producer publishes to. It now subscribes to the union
  of every registry topic plus `auth.topic`, `patient.topic`,
  `configuration.topic` and `audit.topic`, so domain/auth/configuration events
  actually land in the tamper-evident audit database.
- **Tests**: new suites for idempotency (fingerprint incl. key scope, replay,
  memory/Redis stores, error idempotency), the auth dependency (401/403/rbac)
  and metrics (render, recording, histogram buckets). All 10 services + shared
  library remain ruff-clean and green (141 shared + 146 service tests).

## [0.4.1] - 2026-08-18

### Security hardening (enterprise architecture audit — `AUDIT.md`)

- **Gateway route table rewritten** to the real service path contracts
  (`backend/api-gateway/src/api_gateway/routing/routes.py`) covering all 10
  services; EHR disambiguated from patient demographics via `/api/v1/ehr`
  (previously both services claimed `/api/v1/patients/{id}/...`), ehr-portal
  base URL updated. Gateway tests rewritten to the corrected contract.
- **Privilege-escalation fix**: self-service registration now ignores client
  supplied roles and always assigns the default role
  (`register_default_role`); elevated roles require an administrator.
- **RBAC/user-management admin guard**: `create_role`, `create_permission`,
  `assign_roles`, `grant_permissions`, `list_users`, `deactivate_user` and
  ABAC administration endpoints now require the `administrator` role.
- **MFA encryption fail-closed**: TOTP secrets no longer fall back to a
  hardcoded constant; a dedicated `MFA_ENCRYPTION_KEY` is supported and
  deriving secrets from an ephemeral dev-only JWT key is refused outside
  development.
- **Production credential guard**: shared settings refuse the built-in default
  DB password when `EHOS_ENV` is not `development`.
- **Liveness/readiness**: all 10 services now serve `GET /health` (+ `/healthz`)
  via `ehos_common.health`, fixing the previously non-Runnable K8s/Helm probes.
- **CI**: Phase 0 lint/test matrix expanded from 4 to all 10 services; Trivy
  scan now fails the build on HIGH/CRITICAL and covers all built images.
- **Audit report**: `AUDIT.md` — full enterprise architecture audit
  (security, performance, scalability, availability, fault tolerance,
  compliance HIPAA/GDPR/FHIR/HL7/DICOM, audit logging, encryption, role
  permissions, database, API design, AI safety, deployment) with severity
  inventory and 24-item phased remediation plan.

## [0.4.0] - 2026-08-17

### Added

- **Production deployment architecture** (`DEPLOYMENT_ARCHITECTURE.md` + artifacts)
  - Docker single-host deployment: `infrastructure/docker-compose.prod.yml` +
    `.env` example + HAProxy/NGINX edge configs.
  - Kubernetes manifests: `infrastructure/kubernetes/00..16` (namespaces, data
    plane postgres/redis/kafka/minio/qdrant, keycloak, backend + frontend
    deployments, NGINX ingress, cert-manager, HAProxy, prometheus/grafana/loki,
    GPU vLLM inference, backup CronJobs, zero-trust NetworkPolicies).
  - Helm umbrella chart `infrastructure/helm/ehos-platform` (app services +
    data-plane/identity/edge/monitoring dependencies, prod values, templates).
  - CI/CD: `.github/workflows/deploy.yml` (build+push images, helm upgrade to
    dev/staging/prod with environments) + `infrastructure/docker/frontend-spa.Dockerfile`.
  - Monitoring: Grafana dashboard provisioning + `ehos-overview` dashboard.
  - Backup & DR: `infrastructure/backup/` (BACKUP_STRATEGY.md, backup.sh,
    restore.sh, DISASTER_RECOVERY.md, Dockerfile) wired into compose + cronjobs.
  - Verified: compose `config`, YAML parse, kubectl-client schema-less check,
    `helm lint` + full `helm template` render (52 objects).

## [0.3.0] - 2026-08-17

### Added

- **Frontend apps (React + TypeScript + Vite)**
  - `frontend/apps/executive-dashboard` — EHOS Executive Command Center: real-time
    KPI cards (admissions, discharges, revenue, expenses, bed occupancy, waiting
    time, staff utilization, inventory, mortality, readmission) with status,
    deltas and sparklines; interactive dependency-free SVG charts; advisory
    forecasts from the prediction-service (demo fallback); AI executive briefings
    from the ai-service (HospitalGPT, rule-based fallback); PDF print export and
    offline Excel (SpreadsheetML) export. See
    `frontend/apps/executive-dashboard/README.md`.
  - `frontend/apps/ehr-portal` — clinical EHR portal (patient chart, notes, vitals,
    diagnoses, medications, orders, allergies, problem list, medical history,
    timeline) against the ehr-service REST API.
  - `frontend/apps/ai-assistant` — HospitalGPT chat UI (model picker, RAG toggle,
    source citations, feedback, STT/TTS/OCR facades).
  - `frontend/apps/patient-registration` — patient intake/registration flow.
  - AI/prediction dashboard integration: story follows
    `HOSPITALGPT_ARCHITECTURE.md` §9 — `tsc -b` + `vite build`, dev proxies
    `5176 → 8507` (predictions) and `8506` (AI insights).

## [0.2.0] - 2026-08-15

### Added

- **Database Layer: complete PostgreSQL design + executable DDL baseline**
  - `DATABASE_DESIGN.md`: full production design — 27 service-owned databases, common row block, soft delete, `_history` tables, optimistic locking, index rules, monthly partitioning, RLS on PHI, encryption, retention, ER diagrams. Supersedes `DATABASE_SCHEMA_MASTER_DESIGN.md`.
  - `database/<service>_db/V001__init.sql` for every service (platform, patient/scheduling, clinical, operations, AI/knowledge) with PKs, FKs, indexes, CHECK/UNIQUE constraints, history triggers, outbox, RLS.
  - `database/shared/`: roles, extensions, generic history trigger + `ehos_make_history()` helper, partitioned outbox, pg_partman scheduler.
  - `database/apply.py`: applies shared + per-database migrations.
  - `scripts/create_databases.py`: expanded to create all 31 `ehos_*` databases.
  - Verified against live PostgreSQL 16: all 27 migrations apply cleanly; history trigger, soft delete, and outbox behavior confirmed.

## [0.1.0] - 2026-08-14

### Added

- **Phase 0: Foundation Platform**
  - Repository skeleton per `PROJECT_STRUCTURE.md`.
  - `shared/ehos-common`: cross-cutting library (config, structured logging, API response envelope, exceptions, event envelope, security/JWT, DB sessions, Kafka producer, Redis client).
  - `backend/configuration-service`: feature flags & reference configuration, versioned, Redis-cached, emits `ConfigurationUpdated`.
  - `backend/audit-service`: immutable, tamper-evident audit records; REST API + Kafka consumer on `audit.*` topics.
  - `backend/notification-service`: notification templates and delivery via SMS/Email/Push/In-app adapters; consumes domain events.
  - `backend/api-gateway`: routing, JWT validation, rate limiting, request-id correlation, structured access logging.
  - `backend/identity-service`: Keycloak realm definition (realm `ehos`, clients, roles, MFA).
  - `infrastructure/`: docker-compose stack (PostgreSQL 16, Redis 7, Kafka, MinIO, Keycloak) and per-service env templates.
  - `monitoring/`: Prometheus, Grafana, Loki, Tempo baseline configuration.
  - `.github/workflows`: CI/CD baseline with lint, test, build, and security scans (ruff, pytest, trivy, hadolint).
  - Root `Makefile`, `.env.example`, `.gitignore`, `CHANGELOG.md`.

### Documented

- Cross-cutting standards sourced from `CODING_STANDARDS.md`, `EVENT_BUS.md`, `API_DESIGN_STANDARD.md`, and `EHOS_ARCHITECTURE_DESIGN.md`.
