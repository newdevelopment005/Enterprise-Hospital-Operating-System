# EHOS Enterprise Architecture Audit

**Scope:** Complete Hospital Operating System (EHOS)
**Date:** August 2026 · Version 1.0
**Method:** Source-code review of all 10 backend microservices, 4 frontend SPAs, database schemas/migrations, Kubernetes manifests, Helm chart, Docker Compose, CI/CD pipelines, monitoring configs, and backup/DR tooling. Findings cite `file:line`.

---

## Executive Summary

EHOS is an ambitious, well-documented microservice platform. The **documentation layer is strong** (Security Architecture, API Design Standard, Data Governance, Deployment Architecture). However, the **implementation trails the documentation in safety-critical areas**: there is currently **no authentication or authorization enforced on any data-plane service**, several **critical audit/anti-fraud controls are implemented but bypassable**, and the **deployment pipeline would not reach a Ready state** (readiness probes hit endpoints that don't exist; the Helm pod securityContext cannot schedule the root-running images).

Overall maturity: **Documented-but-unlit production path.** The gap is not code volume but *enforcement of the stated security model at runtime*.

### Severity inventory

| Severity | Count |
|---|---|
| CRITICAL | 7 |
| HIGH | 14 |
| MEDIUM | 18 |
| LOW / POSITIVE | 14 |

---

## 1. Security

### 1.1 CRITICAL — No authentication on data-plane services
`patient-service`, `ehr-service`, `ai-service`, `knowledge-service`, `prediction-service`, `configuration-service`, `notification-service` expose **every** endpoint without any JWT/role dependency (`backend/*/src/*/api/routes.py`). The gateway is the only guard (`api_gateway/security/middleware.py:56-91`) and its route table covers only a subset of services (`routing/routes.py:19-35`) — and several of those entries point at path prefixes that no service actually exposes (see §6). Any client that can reach a service port (port-forward, namespace compromise, compose host) can read/write all patient and clinical records.

### 1.2 CRITICAL — Registration allows self-assigned privilege escalation
`auth_service.py:219-220` assigns client-supplied `request.roles` verbatim; `rbac_service.py:51-54` auto-creates any missing role code. Registering `{"roles": ["administrator"]}` yields an administrator token.

### 1.3 CRITICAL — RBAC & user administration endpoints are unauthenticated-by-role
`routes.py:326-354, 389-409` (assign roles, grant permissions, deactivate any user, create roles/permissions) require only *any* valid token (`CurrentUser`). A legitimate low-privilege user can grant themselves any permission and disable others. No `administrator` guard exists.

### 1.4 HIGH — Dual JWT trust chains never connect
Gateway validates against Keycloak JWKS (`main.py:25`, `ehos_common/security.py:48-68`, audience `account`); the custom authentication-service issues RS256 tokens (`token_service.py:72`) with issuer `http://localhost:8500` and audience `ehos-api`, signed by an **ephemeral key regenerated on each startup** when `JWT_PRIVATE_KEY_PEM` is unset (`configuration.py:70-88`). Production manifests provide no key material. Consequences: (a) tokens from the auth-service cannot pass the gateway; (b) every restart invalidates every issued token; (c) HMAC-divergent MFA secret decryption (below).

### 1.5 HIGH — MFA secrets encrypted with an insecure default
`mfa_service.py:36` falls back to the literal constant `"ehos-dev-signing-key"` when no key material exists, and otherwise reuses the JWT signing key (key-divergence). A public constant plus a reproducible key derivation means TOTP secrets are trivially decryptable on any misconfigured deploy.

### 1.6 HIGH — PHI in transit is plaintext
- Kafka listeners are `PLAINTEXT` with `AUTO_CREATE_TOPICS=true` (`docker-compose.prod.yml:112-116`; `05-kafka.yaml:42-45`) though prod Helm values already declare SASL (`values-prod.yaml:25-27`) — no `ehos-kafka-sasl` secret is provisioned.
- `PatientRegistered`/`PatientMerged` events carry firstName/lastName/MRN in clear text over the bus (`patient_service.py:240-244, 421-426`).
- No mTLS/Istio/Linkerd; all inter-service traffic and Keycloak use HTTP (`08-keycloak.yaml:37`).

### 1.7 HIGH — Committed plaintext/placeholder secrets in working manifests
`04-redis.yaml:63-64` (`change-me-redis`), `07-qdrant.yaml:56-58` (`change-me-qdrant`), `values.yaml:91` / `values-prod.yaml:66` (`CHANGE_ME` Grafana), plus the placeholder secrets set in `01-secrets.example.yaml`. Non-example manifests should carry provable credentials only (Sealed Secrets/SOPS/External Secrets), never literal values.

### 1.8 MEDIUM — Required secrets never provisioned
`ehos-service-env` (referenced by every Helm service), `ehos-kafka-sasl` (prod values), `ghcr` imagePullSecret (`deploy.yml:91`), and `AUTH_JWT_PRIVATE_KEY`/`AUTH_JWT_PUBLIC_KEY` do not exist in any manifest. The deploy workflow has no secret-provisioning step.

### 1.9 MEDIUM — Rate limiting is IP-only and sync-in-async
`middleware.py:34-53` uses a synchronous `redis.Redis` inside an async middleware, blocking the event loop; the bucket key is the raw peer IP (the ingress Pod IP in K8s, collapsing all tenants into one bucket). `/api/v1/auth` is not behind the gateway, so login has **no per-IP throttle** (distributed credential-stuffing vector).

### 1.10 MEDIUM — Unauthenticated `/docs` and OpenAPI on every service
`main.py:56-58` (all services) expose full API schemas (including PHI field names) wherever a service is reachable.

### 1.11 MEDIUM — `/api/v1/patients/{id}/timeline` is registered by BOTH patient-service and ehr-service
Two services claim the same path under the same gateway namespace (`patient_service/api/routes.py` and `ehr_service/api/routes.py`). A prefix-routing gateway cannot disambiguate; runtime behavior depends on which route table wins. Resolved in this audit's remediation (EHR moved to `/api/v1/ehr`).

### 1.12 MEDIUM — No signed identity propagation downstream
`proxy/handler.py:31-40` forwards raw `Authorization` + all headers; services never validate them and receive no injectable `X-User-Id`/`X-Roles`. Downstream audit attribution (`created_by`) is therefore always NULL (§3.3).

### 1.13 POSITIVE
- Parameterized ORM queries everywhere — no SQL interpolation found (§2.4).
- No hardcoded API keys in Python source.
- Gateway forwards no request bodies into logs (`handler.py:56-67`); error handlers return generic envelopes without stack traces (`ehos_common/api.py:84-89`).
- FastAPI `SecretStr` used for passwords; `EmailStr`/length bounds validated (`auth_service/dto/schemas.py`).

---

## 2. Authentication & Session Management (authentication-service)

Implemented (verified + unit-tested): bcrypt(12 rounds) hashing, password policy (12+ chars, character classes, common-password denylist, history 5, max age 90d), account lockout (5 attempts/15 min), refresh-token rotation with reuse detection, session revocation, logout, TOTP MFA enrollment/verify (`mfa_service.py`), RBAC and ABAC engines, RS256 signing, token introspection.

Findings:
- **HIGH — registration privilege escalation** (§1.2).
- **HIGH — ephemeral signing keys** (§1.4): breaks horizontal scaling and session durability.
- **HIGH — admin endpoints unguarded** (§1.3).
- **MEDIUM — username enumeration**: distinct `409 USERNAME_TAKEN` vs `422 WEAK_PASSWORD` responses (`auth_service.py:200-201`).
- **LOW — only TOTP implemented**; SMS/EMAIL/WEBAUTHN documented in `schemas.py:57` but unimplemented.
- **HIGH (compliance) — locally bypassable lockout**: 5-failure lockout can be trivially circumvented by rotating accounts since there is no IP-based throttle on `/login` (auth-service is not routed through the gateway).

---

## 3. Role Permissions & Authorization (RBAC/ABAC)

- **Engine: implemented.** Role/permission tables (`entity/models.py:138-184`), claims embedded in the JWT (`token_service.py:59-71`), ABAC policy engine default-deny with tests (`abac_service.py:106-121`).
- **Enforcement: effectively absent.** The gateway checks a role for exactly one route (`routes.py:23`, `/configuration`→administrator). No data-plane service evaluates roles, permissions, or ABAC conditions. "Doctor sees only own patients" (the zero-trust model's core requirement) is **not implemented anywhere** — every query is scoped by a `patient_id` taken from the URL, not by the authenticated actor (`ehr_service.py:63-69`).
- **Audit attribution absent** — `created_by`/`updated_by` on clinical/PHI writes are always NULL because the gateway never injects the authenticated subject and services never read it.
- **Missing ABAC on retrieval**: `knowledge_service.py:306-311` hardcodes `permitted=True`.

---

## 4. Database

- **Migrations: not wired.** Alembic is a shell (no `versions/` revisions; `ehr-service`/`audit-service` have no alembic at all). **Tables are created at app start via `create_all`** (`main.py:29`, `ehos_common/db.py:48-54`) despite a comment claiming production uses Alembic — nothing else runs. `create_all` silently drops everything in the SQL: partial unique indexes (MRN, username), GIN trgm, RLS policies, history triggers, partitions, GRANTs, the outbox table.
- `database/apply.py` is **not idempotent**: replays every `V*__*.sql` and re-CREATEs tables (`apply.py:103-106`); no `schema_migrations` ledger exists anywhere.
- **CRITICAL — MRX/unique races**: MRN is allocated via `SELECT max(mrn)+1` (`patient_service.py:65-73`); under `create_all` the partial unique index that would catch collisions is absent → duplicate patient MRNs at high concurrency.
- **ORM/SQL divergence**: `audit-service` maps `audit_records` (`models.py:17-39`) while the DDL defines `audit_logs`/`events`/`event_sagas` with a different hash-chain shape; the correct `chain_hash` is never written by code.
- **PHI at rest in plaintext**: national_identifier, insurance card/policy numbers, raw photo bytes, and full clinical note text are stored unencrypted; no column encryption/TDE/pgcrypto.
- **RLS is inconsistent**: `patient_contacts`, `patient_links`, `patient_timeline`, `encounters`, `vital_signs`, `care_plans`, `referrals`, `clinical_note_versions/amendments` carry no RLS.
- **Connection pool not tuned**: `create_async_engine(url, pool_pre_ping=True)` only (`db.py:45`); default Pool; Postgres `max_connections` default 100 vs ~9 services × 2-3 replicas → connection exhaustion risk.
- **Duplicated domains**: allergies defined in both `ehr_db` and `prescription_db` with conflicting severity enums; JSONB `contact_info/emergency_contact` on `patients` coexist with normalized tables.
- `infrastructure/docker-compose.yml` and `03-postgres.yaml` mount a non-existent `./database/init` source dir; the real init SQL lives at `infrastructure/database/init/001_create_databases.sql` — init never runs.

**Positive:** timezone-aware timestamps (`TIMESTAMPTZ`, `DateTime(timezone=True)`) and soft-delete columns used consistently.

---

## 5. API Design

- **Consistent envelope**: `{success, data|errorCode|message, timestamp}` enforced by `ehos_common/api.py`; stable error codes.
- **Good REST hygiene**: versioned `/api/v1`, proper 201 on create, structured 422/404/500.
- **CRITICAL — route table / service contract mismatch**: gateway forwards `/api/v1/configuration`, `/api/v1/audit`, `/api/v1/notifications` but the services expose `/api/v1/entries|flags|all`, `/api/v1/records|integrity`, `/api/v1/templates|send` → 404/502 in any real deployment; the tests (`test_routing.py`) encode this broken contract. (§1.11, §6)
- **Missing API + platform conventions**: no pagination envelope on list endpoints beyond `limit`/`offset` query params; no correlation/request-id propagation downstream; no idempotency keys on POST; no `Retry-After`/`429` semantics; CORS `allow_origins=[]` (safe, undocumented); OpenAPI lacks securitySchemes on every service.
- Raw-body parsers bypass Pydantic: `ehr_service/routes.py:190-194` (`await request.json()`), gateway forwards unvalidated bodies (`handler.py:35`).

---

## 6. Deployment Status

Docker Compose prod + K8s + Helm + CI exist and are validated (compose `config`, `helm lint`, `helm template` → 52 objects). **Deploy-blocking defects:**

- **Readiness probes point at non-existent `/health`** on 10 services (only notification-service defines it; `notification_service/api/routes.py:70-72`) → pods never Ready; Helm liveness on `/health` → restart loop.
- **Helm pod securityContext is unschedulable**: `runAsNonRoot: true` (`templates/deployment.yaml:31`) but every Dockerfile runs as root (no `USER`) → `CreateContainerConfigError`.
- **Compose bind-mounts are broken**: `docker-compose.prod.yml:83` mounts `../database/init` and `:387` `../monitoring/grafana/dashboards` — both paths don't exist (real: `infrastructure/database/init`, `monitoring/grafana/provisioning/dashboards`).
- **NetworkPolicies break the cluster**: default-deny (`16-network-policies.yaml`, helm `networkpolicy.yaml`) with almost no allow rules — no DNS egress, no data-plane→kube-apiserver, no monitoring scrape ingress except api-gateway. Applying them as-is severs all traffic including DNS.
- **No PDB** for api-gateway/kafka/keycloak/minio (only inference). Quorum components (Kafka StatefulSet, MinIO 4-node) lack anti-affinity/topology spread (only Keycloak has `podAntiAffinity`).
- **Postgres is single-replica** (no HA/failover); Kafka/MinIO persistence PVCs rely on a single `Retain` StorageClass.
- **AUTH_JWT_PRIVATE_KEY not provisioned** (§1.4).

### CI/CD
- Image tags and Helm `--set` wiring are correct (`deploy.yml:89-90,116-117,144-145`); three environments gated to `develop`/`main`/`v*`.
- **Gaps**: no security gate before prod (Trivy runs on api-gateway only, never fails the build; `phase0-ci.yml` tests 4 of 10 services; runs only on push/PR to main/develop — never on `v*` tags, so the prod path skips tests entirely); no image signing/attestation/SBOM; `REGISTRY_ORG: your-org` placeholder; `ghcr` pull secret not provisioned; smoke test checks only two workloads.

---

## 7. Monitoring & Observability

- **Alert rules: 3 defined, 2 dead.** `13-monitoring.yaml:36-54` has `EHOSServiceDown`, `EHOSPostgresHighConnections`, `EHOSKafkaLag` — but no postgres-exporter or kafka-exporter is deployed, so the PG/Kafka metrics don't exist. `monitoring/prometheus/rules/ehos-alerts.yml` mixes a LogQL expression into a Prometheus rule file (invalid). Referenced `EHOSBackupMissing` alert does not exist.
- **ServiceMonitors scrape `/health`** (correct path would be `/metrics`) and `serviceMonitorSelector` won't match `release: prometheus` under a chart release named `ehos`. No service exports `/metrics` at all.
- **Grafana datasources auto-provision correctly** (Prometheus/Loki/Tempo) but `grafana.ini` is authored as YAML inside an INI parser; a dashboard references metric sources that don't exist.
- **Loki/Tempo ship no logs/traces**: no Promtail/Alloy shipper; no OTLP instrumentation in any service.
- GPU has dcgm-exporter but no ServiceMonitor; network policies block scraping (§6).

---

## 8. Backup & Disaster Recovery

- **RPO claim unrealizable**: `BACKUP_STRATEGY.md:10` promises RPO ≤15 min via Postgres WAL, but **no WAL archiving exists** (`wal_level`/`archive_command`, wal-g, pgBackRest all absent); effective RPO is the daily CronJob ≈ 24h. `restore.sh` documents `--pitr` but implements no such flag.
- **Backups are not encrypted**: `backup.sh`/`restore.sh`/CronJobs write plaintext `pg_dump` and `mc mirror`; the documented age/SOPS encryption key (`01-secrets.example.yaml:73`) is never used.
- **CRITICAL — the audit database is not backed up**: `backup.sh:28` and `15-backup.yaml:24-26` list `ehos_platform/ehos_clinical/ehos_ai`, but the deployed DBs are `ehos_keycloak/ehos_configuration/ehos_audit/ehos_notification/ehos_gateway`. The HIPAA-relevant tamper-evident audit trail is lost on any failure.
- Qdrant "snapshot" stays on the node (never copied offsite); Kafka is claimed backed up but has no mirror; offsite default endpoint is a health URL not an S3 endpoint (`01-secrets.example.yaml:69`).
- No object-lock/immutability on backup targets; no automated restore drill; DR metrics exist only in prose.

---

## 9. Fault Tolerance, Availability & Scalability

- **Implemented**: resource requests/limits on all K8s workloads; HPA on api-gateway only; Kafka KRaft 3-broker RF3; MinIO 4-node; graceful degradation for Kafka producer outage.
- **Gaps**: no PDBs (§6); no startupProbe anywhere; single Postgres; no horizontal-scaling isolation for auth (ephemeral JWT keys); connection-pool exhaustion risk; no memory-based HPA; no topology spread; no preStop/terminationGracePeriods.

---

## 10. Compliance

| Standard | Status | Evidence / Gap |
|---|---|---|
| **HIPAA** | PARTIAL | Audit hash-chain append-only is implemented (`audit_service.py:22-68`); BUT: audit DB not backed up, audit events don't flow in (topics mismatch `auth.topic` vs `audit.topic`), audit REST endpoints unauthenticated → forgeable "immutable" records, PHI columns unencrypted, no created_by attribution, no access-log retention policy. |
| **GDPR** | PARTIAL | Consent records + soft-delete implemented; **no right-to-erasure/delete API** (zero `@router.delete` in patient-service), no export/portability endpoint, no retention scheduler, no DPA artifact. |
| **FHIR R4** | DOC-ONLY | `FHIR_HL7_INTEROPERABILITY.md` defines intent; no FHIR resources/servers, mapping tables, or endpoints in any service. |
| **HL7 v2** | DOC-ONLY | No message parser/listener/transformer code. |
| **DICOM** | DOC-ONLY | No DICOM C-STORE/SCU endpoint; imaging surfaced only as opaque blobs. |
| **AUDIT** | PARTIAL | chain-hash integrity OK; gap: unauthenticated writer, no bus wiring, no backup, no SIEM/offsite archive, no immutability on storage target. |
| **ENCRYPTION** | PARTIAL | TLS edge-only; Kafka/PG/Redis clear; PHI columns clear; keys not managed/rotated; no KMS/HSM. |
| **ROLE PERMISSIONS** | PARTIAL | RBAC/ABAC engines exist; zero enforced data-plane authorization. |
| **AI safety** | PARTIAL→LOW | see §11; safety layer documented but inert; prompt injection; unauthenticated retrieval; cosmetic approvals. |

---

## 11. AI Safety & Model Governance

- **CRITICAL — prompt injection**: user text concatenated into prompt templates with `str.replace` and no sanitization/instruction-hierarchy (`ai_service.py:179-186`, `engines.py:201-214`, `agents.py:463-471`).
- **HIGH — safety layer documented, not enforced**: `safety_rules` on prompt templates are stored/serialized but never read for decisioning; `safety_flags` never populated; no allowlist/keyword block/guardrail in the codebase.
- **HIGH — unauthenticated AI + IDOR**: any caller can POST `/api/v1/ai/chat`, and conversations/memories/transcripts are listable/scopable by caller-supplied `user_id` with no ownership check (`ai_service.py:255-265`); STT/OCR logged under `user_id=uuid.UUID(int=0)`.
- **HIGH — APPROVED model registry is bypassable**: `register_model(..., approved=payload.approved)` honors the request flag; `load_model` force-sets `APPROVED`; `approver_id` is caller-supplied and unverified (`dto/schemas.py:30`). Human-in-the-loop is cosmetic.
- **HIGH — production inference silently falls back to a mock**: manifests set `AI_INFERENCE_ADAPTER=vllm` + `AI_INFERENCE_URL`, but `AiSettings` has no such fields (extra="ignore") and the adapter factory only knows mock/ollama/llamacpp; **vLLM GPU server is never used**; model requests have no API key and no URL allowlist.
- **HIGH — RAG grounding is metadata-only**: the prompt's `{{context}}` contains doc titles/scores, never chunk content — the model cannot actually read the retrieved guidelines; retrieval is unscoped by role/tenant, and unreviewed documents (`status=INDEXED`) are searchable.
- **MEDIUM — hardcoded clinical gates without provenance**: forecast target thresholds (WAPE 0.15-0.25, MAPE 0.15, MAE 0.10/3.0, PRECISION 0.60) and a drift auto-deprecate at WAPE>0.20 with no citation/owner/review trail; confidence defaults to a fabricated `0.90`; embedding store is Postgres JSONB brute-force cosine, not Qdrant/pgvector, with `top_k` up to 50 and `similarity_threshold=0.1`.
- **Positive**: append-only `ai_requests` audit recording with hashes; `ChatOut.sources` citations; forecast interval bands q10/q90; drift reconciliation (WAPE); approval gates on agent action execution.

---

## 12. Performance

- Async FastAPI + asyncpg/httpx throughout — appropriate stack.
- **Concerns**: sync Redis in the async gateway middleware; brute-force cosine retrieval at scale; no indexes on hot columns under `create_all` (§4); unbounded `top_k`/threshold; token counts estimated by whitespace regex not tokenizer; PG pool exhaustion at replica counts.
- No load tests/perf baselines, no P95/P99 targets, no profiling CI in repo.

---

## Remediation Plan (priority order)

### Phase 1 — Security & deploy blockers (this audit's delivered fixes)
1. ✅ Gateway route table rewritten to real service contracts + EHR disambiguated to `/api/v1/ehr` (+ frontend base updated).
2. ✅ Registration client-supplied roles ignored; default role assigned.
3. ✅ Administrator-only guard on RBAC/user-management/ABAC-admin endpoints.
4. ✅ MFA encryption keyed fail-closed (no hardcoded fallback).
5. ✅ `/health` (and `/metrics`) served from all services; readiness/liveness/ServiceMonitor align.
6. ✅ Production credential guard (refuse default DB password outside `development`).

### Phase 2 — Deployment correctness
7. Compose bind-mount paths fixed to real dirs.
8. NetworkPolicies rewritten: DNS egress + gateway-centric flows + monitoring scrape allowances; add PDBs, startupProbes, anti-affinity, topology spread.
9. `ehos-service-env`, `ehos-kafka-sasl`, `ghcr`, `AUTH_JWT_*`, `POSTGRES_PASSWORD` secrets provisioned in CI bootstrap; remove committed Secret objects; Kafka SASL_SSL; psql/redis TLS.
10. Replace literal `CHANGE_ME` Grafana password; switch secrets to Sealed Secrets/SOPS.

### Phase 3 — True zero-trust & audit integrity
11. Unified identity: single issuer (Keycloak) or publish auth-service JWKS to the gateway; shared, persisted signing keys; gateway injects signed `X-User-Id`/`X-Roles`; services enforce `required_role` + ABAC evaluation ("doctor sees own patients").
12. Per-service `created_by` attribution on all PHI writes; DB trigger to require it.
13. Authentication/patient events published to `audit.topic`; audit REST write path restricted to trusted in-cluster caller + `auditor` role; audit DB added to backups + SIEM archive + retention policy.

### Phase 4 — Data, migrations, encryption
14. Alembic revisions generated per service; `create_all` removed; idempotent `apply.py` with `schema_migrations` ledger; reconcile `infrastructure/database/init` mount.
15. Fix MRN allocation with a sequence/identity; align ORM ↔ SQL (partial unique indexes, partitions, audit chain shape).
16. Column-level encryption for PHI (national_identifier, insurance, photos, notes) via KMS; enable RLS on all patient/clinical tables; tune connection pools; postgres HA pattern.

### Phase 5 — AI safety & clinical governance
17. Prompt-hardening: templated instruction hierarchy + input classification + output filter; enforce `safety_rules`; disclaimers as first-class output field.
18. Real vLLM/OpenAI-compatible adapter with API key + URL allowlist; fail loud on unknown adapter.
19. RAG: inject bounded chunk content into context; APPROVED-only retrieval; per-role/tenant scoping; pgvector/Qdrant with sane threshold/top_k; gate provenance for clinical thresholds.

### Phase 6 — Compliance & operations
20. GDPR: DELETE/right-to-erasure + export endpoints, retention scheduler, DPA.
21. FHIR R4 resource mapping layer, HL7 v2 listener, DICOM integration point (phase plan).
22. WAL archiving (wal-g/pgBackRest) to make RPO 15 min real; `--pitr` restore; backup encryption (age/SOPS) + object-lock; restore-drill CronJob; backup all DBs incl. `ehos_audit`.
23. Observability: per-service `/metrics` (prometheus + Instrumentator), Promtail/OTLP shippers, fix alert rules, backup-freshness alert, SLOs.
24. CI: test+scan all 10 services, gate prod on security scan, cosign attestation + SBOM, prod approval; raw-manifest `envsubst` job or drop raw manifests in favor of Helm.

---

## Scorecard

| Dimension | Grade | Notes |
|---|---|---|
| Security | D+ | Engines exist; enforcement missing |
| Authentication | B+ | Excellent depth; trust-chain & key problems |
| Role Permissions | D | Engine yes, enforcement no |
| Database | D+ | Migrations broken; PHI plaintext; races |
| API Design | B- | Consistent envelope; route contract broken |
| AI Safety | D | Injection + cosmetic HITL + mock-in-prod |
| Availability | C | Replicas/limits yes; PDB/probes/HA no |
| Fault Tolerance | C- | Quorum via CP; single PG; no PDB/anti-affinity |
| Scalability | D+ | Auth keys + PG pool + no autoscale beyond gateway |
| Monitoring | D+ | Valid dashboards; dead rules; no log/trace path |
| Encryption | D | Edge TLS only; PHI & bus in clear |
| Audit Logging | C+ | Hash-chain good; wiring/backup/auth missing |
| Compliance | D+ | Docs strong, controls partial; FHIR/HL7/DICOM doc-only |
| Deployment | C- | 3 deploy-blocking defects; CI 4/10 services |
| Backup/DR | D | Unscheduled audit DB, unencrypted, RPO false |