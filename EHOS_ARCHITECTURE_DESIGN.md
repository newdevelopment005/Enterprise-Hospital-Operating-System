# EHOS — MASTER ARCHITECTURE DESIGN

**System:** Enterprise Hospital Operating System (EHOS)
**Document Type:** Complete Architecture Design (no application code)
**Version:** 1.0.0
**Status:** Approved baseline for all subsequent implementation steps

---

## TABLE OF CONTENTS

1. Architecture Philosophy
2. Folder Structure
3. Microservices
4. API Design
5. Event Bus
6. Database Architecture
7. AI Architecture
8. Authentication & Authorization
9. API Gateway
10. Deployment Architecture
11. Monitoring
12. Logging
13. Security Zones & Network
14. Cross-Cutting Standards
15. Implementation Build Order

---

# 1. ARCHITECTURE PHILOSOPHY

EHOS is a distributed, event-driven, AI-native hospital operating platform.

Non-negotiable architectural rules:

- **No monolith.** Every domain is an independently deployable service.
- **Database-per-service.** No service reads another service's database directly.
- **API-first.** All inter-service and external communication is via versioned, documented APIs.
- **Event-driven.** Every significant business action publishes an immutable, versioned event.
- **Local-first.** The platform runs fully on hospital infrastructure; no mandatory cloud.
- **Zero trust.** Every request, service, device, and AI agent is authenticated and authorized.
- **AI assists, never decides.** Clinical decisions remain with licensed professionals.

Communication patterns:

| Pattern | Use |
|---|---|
| REST (synchronous) | Queries, transactions, user interactions, configuration |
| Kafka (asynchronous) | Domain events, automation, analytics, AI triggers, long workflows |
| WebSocket / SSE | Real-time queues, emergency alerts, live dashboards |

---

# 2. FOLDER STRUCTURE

```
ehos/
│
├── docs/                        # All architecture & policy documents
│   ├── MASTER_BLUEPRINT.md
│   ├── SYSTEM_OVERVIEW.md
│   ├── ARCHITECTURE.md
│   ├── DATABASE_DESIGN.md
│   ├── API_SPECIFICATION.md
│   ├── EVENT_CATALOG.md
│   ├── AI_PLATFORM.md
│   ├── SECURITY.md
│   ├── DEPLOYMENT.md
│   ├── MONITORING.md
│   └── ROADMAP.md
│
├── backend/                     # Microservices (Python FastAPI, one dir per service)
│   ├── api-gateway/
│   ├── identity-service/        # AuthN facade over Keycloak
│   ├── audit-service/
│   ├── notification-service/
│   ├── configuration-service/
│   ├── patient-service/
│   ├── appointment-service/
│   ├── queue-service/
│   ├── ehr-service/
│   ├── clinical-documentation-service/
│   ├── prescription-service/
│   ├── pharmacy-service/
│   ├── laboratory-service/
│   ├── radiology-service/
│   ├── emergency-service/
│   ├── surgery-service/
│   ├── bed-service/
│   ├── telemedicine-service/
│   ├── billing-service/
│   ├── insurance-service/
│   ├── finance-service/
│   ├── inventory-service/
│   ├── procurement-service/
│   ├── hr-service/
│   ├── payroll-service/
│   ├── reporting-service/
│   └── workflow-service/        # Clinical workflow / state machine engine
│
├── frontend/                    # React + TypeScript (Vite)
│   ├── doctor-portal/
│   ├── nurse-portal/
│   ├── patient-portal/
│   ├── pharmacy-console/
│   ├── laboratory-console/
│   ├── radiology-console/
│   ├── admin-console/
│   ├── finance-console/
│   ├── executive-dashboard/
│   └── shared-ui/               # Design system, shared components
│
├── mobile/                      # Flutter
│   ├── patient-app/
│   ├── doctor-app/
│   ├── nurse-app/
│   ├── logistics-app/
│   └── shared/
│
├── ai-platform/                 # Python local AI services
│   ├── ai-gateway/
│   ├── model-service/
│   ├── prompt-service/
│   ├── embedding-service/
│   ├── rag-service/
│   ├── knowledge-service/
│   ├── speech-service/          # Whisper
│   ├── ocr-service/             # PaddleOCR / Tesseract
│   ├── agent-service/           # AI agent runtime + orchestrator
│   ├── prediction-service/      # Forecasting (PyTorch/sklearn)
│   ├── executive-ai-service/
│   └── evaluation-service/
│
├── integrations/                # Healthcare interoperability adapters
│   ├── hl7/
│   ├── fhir/
│   ├── dicom/
│   ├── pacs/
│   ├── insurance/
│   ├── sms-email/
│   └── medical-devices/
│
├── database/                    # Migrations, seeds, diagrams
│   ├── migrations/              # Per-service migration scripts
│   ├── seeds/                   # Approved reference data (ICD/LOINC/drugs)
│   ├── diagrams/
│   └── scripts/
│
├── infrastructure/
│   ├── kubernetes/              # Manifests + namespaces
│   ├── helm/                    # Helm charts per service
│   ├── terraform/
│   ├── ansible/
│   ├── networking/
│   ├── storage/
│   ├── gpu/
│   └── secrets/                 # Vault config (no secrets in git)
│
├── deployment/
│   ├── docker-compose/          # Local + dev orchestration
│   ├── staging/
│   ├── production/
│   └── disaster-recovery/
│
├── monitoring/
│   ├── prometheus/{config,rules,alerts}
│   ├── grafana/{dashboards,providers}
│   ├── loki/
│   ├── tempo/
│   └── alertmanager/
│
├── security/
│   ├── policies/
│   ├── certificates/
│   ├── compliance/
│   └── vulnerability-scans/
│
├── shared/                      # Generic cross-service libraries (no domain logic)
│   ├── authentication/          # JWT validation helpers
│   ├── events/                  # Event envelope + producer/consumer SDK
│   ├── logging/
│   ├── auditing/
│   ├── validation/
│   ├── configuration/
│   └── healthcare/              # ICD/FHIR/terminology helpers
│
├── testing/                     # Cross-cutting test tooling
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── performance/
│   ├── security/
│   └── e2e/
│
├── assets/
├── config/{development,testing,staging,production}
├── Makefile                     # Dev entry points (make up, make test, make seed)
├── docker-compose.yml           # Development environment
└── README.md
```

**Naming rules:** lowercase kebab-case directories/DBs, snake_case tables/columns, PascalCase classes, camelCase functions/variables. Standard abbreviations allowed (`ehr`, `icu`, `hl7`, `fhir`).

---

# 3. MICROSERVICES

All services are **independently deployable, testable, scalable, replaceable**, own their DB schema, publish/consume events, and expose `/health`, `/readiness`, `/liveness`.

## 3.1 Platform Services

| Service | Ownership | Primary Events (publish) |
|---|---|---|
| `api-gateway` | Routing, TLS termination | — |
| `identity-service` | Facade over Keycloak; user lifecycle | `UserCreated`, `UserDeactivated` |
| `audit-service` | Immutable audit records | consumes all |
| `notification-service` | SMS, email, push, in-app | consumes events |
| `configuration-service` | Feature flags, reference config | `ConfigurationUpdated` |
| `workflow-service` | Clinical workflow/state machine engine | `WorkflowStarted`, `WorkflowTransitioned` |

## 3.2 Patient & Scheduling

| Service | Ownership | Primary Events |
|---|---|---|
| `patient-service` | Patient master data, demographics, consents, MPI | `PatientRegistered`, `PatientUpdated`, `PatientMerged`, `ConsentChanged` |
| `appointment-service` | Appointments, schedules, availability | `AppointmentCreated`, `AppointmentRescheduled`, `AppointmentCancelled`, `AppointmentCompleted` |
| `queue-service` | Outpatient/emergency queues, digital queue status | `QueueJoined`, `QueueAdvanced`, `QueueCompleted` |

## 3.3 Clinical

| Service | Ownership | Primary Events |
|---|---|---|
| `ehr-service` | Encounters, diagnoses, history, versioned medical records | `EncounterCreated`, `DiagnosisRecorded`, `ClinicalNoteCreated`, `TreatmentRecorded` |
| `clinical-documentation-service` | Clinical notes, SOAP/progress/discharge summaries (incl. AI drafts) | `DocumentCreated`, `DocumentApproved` |
| `prescription-service` | Prescriptions, medication orders, allergy and interaction checks | `PrescriptionCreated`, `PrescriptionCancelled` |
| `pharmacy-service` | Dispensing, medication lifecycle, controlled drugs | `MedicationDispensed`, `MedicationReturned`, `MedicationExpired` |
| `laboratory-service` | Lab orders, samples, results, verification | `LabOrderCreated`, `SampleCollected`, `LabResultAvailable`, `LabResultVerified` |
| `radiology-service` | Imaging requests, studies, reports; DICOM/PACS | `ImagingRequested`, `ImagingCaptured`, `RadiologyReportCompleted` |
| `emergency-service` | ED registration, triage priority, ED workflows | `EmergencyRegistered`, `TriageAssigned`, `EmergencyActivated` |
| `surgery-service` | Surgical scheduling, theatre allocation, perioperative flow | `SurgeryScheduled`, `SurgeryStarted`, `SurgeryCompleted` |
| `bed-service` | Bed assignment, occupancy, transfers | `BedRequested`, `BedAssigned`, `BedReleased` |
| `telemedicine-service` | Video/audio consultation, remote monitoring | `TelehealthStarted`, `TelehealthCompleted` |

## 3.4 Enterprise / Operations

| Service | Ownership | Primary Events |
|---|---|---|
| `billing-service` | Charges, invoices, payments, receipts | `ChargeCreated`, `InvoiceGenerated`, `PaymentReceived` |
| `insurance-service` | Coverage verification, claims, authorizations | `ClaimSubmitted`, `ClaimStatusChanged` |
| `finance-service` | General ledger, accounting, financial integrity | `JournalPosted`, `TransactionRecorded` |
| `inventory-service` | Stock, movements, expiry, reorder thresholds | `StockReceived`, `StockConsumed`, `StockLow`, `StockExpired` |
| `procurement-service` | Purchase orders, suppliers, approvals | `PurchaseRequested`, `PurchaseApproved`, `PurchaseOrderPlacement` |
| `hr-service` | Employees, departments, rostering, credentials | `EmployeeCreated`, `ShiftAssigned`, `CredentialExpired` |
| `payroll-service` | Payroll inputs, payroll runs, payslips | `PayrollGenerated` |
| `reporting-service` | Report generation, exports | consumes events |

## 3.5 AI Services

| Service | Ownership | Notes |
|---|---|---|
| `ai-gateway` | Entry point for ALL AI requests; authz, routing, safety, audit | Never callable directly from UI except through this |
| `model-service` | Model registry, versions, approval status | `ModelUpdated`, `ModelApproved` |
| `prompt-service` | Managed prompt templates, policies | — |
| `embedding-service` | Embedding generation (BGE/E5/Nomic) | — |
| `rag-service` | Retrieval, citation, knowledge grounding | — |
| `knowledge-service` | Document ingestion → vector store (Qdrant) | `KnowledgeDocumentIndexed` |
| `speech-service` | Whisper transcription (local) | — |
| `ocr-service` | PaddleOCR/Tesseract processing | — |
| `agent-service` | Agent runtime + orchestrator; human-approval workflow | `AIRequestCreated`, `AIResponseGenerated`, `AgentActionPendingApproval` |
| `prediction-service` | Demand/staffing/inventory/risk forecasting | `PredictionGenerated` |
| `executive-ai-service` | Summaries, KPIs, command-center insights | — |
| `evaluation-service` | Model/agent eval, drift, feedback | — |

**Cross-cutting rule:** AI services may not access production databases directly. They consume events and read through approved, permission-scoped data APIs.

---

# 4. API DESIGN

## 4.1 Conventions

- REST over HTTPS via API Gateway.
- Base path: `https://<gateway>/api/v1/<resource>` (v2+ by negotiated evolution).
- Every protected endpoint requires `Authorization: Bearer <access_token>`.
- OpenAPI 3.x spec per service (`openapi.yaml`) — schema-validated in CI.
- Pagination: `?page=1&size=50`; filtering `?department=cardiology`; sorting `?sort=date`.
- Versioning: additive-first; never break existing clients without deprecation cycle.
- Internal service calls: OAuth2 client-credentials tokens + mTLS where sensitive.
- Healthcare surface: FHIR R4/R5 endpoints on integration layer (`/fhir/r4/...`), HL7 v2 via adapters, DICOM via PACS gateway.

## 4.2 Standard Response Envelope

Success:
```json
{ "success": true, "data": {}, "requestId": "abc123", "timestamp": "2026-08-14T00:00:00Z" }
```

Error:
```json
{ "success": false, "error": { "code": "PATIENT_NOT_FOUND", "message": "Patient record does not exist" }, "requestId": "abc123", "timestamp": "..." }
```

HTTP semantics: 200 OK, 201 Created, 400 Bad Request, 401 Unauthenticated, 403 Forbidden, 404 Not Found, 409 Conflict, 500 Internal.

## 4.3 Core Endpoint Catalog (baseline)

| Service | Endpoints (representative) |
|---|---|
| identity | `POST /auth/login`, `POST /auth/logout`, `POST /auth/refresh`, `GET /users/profile` |
| patient | `POST /patients`, `GET /patients/{id}`, `PUT /patients/{id}`, `GET /patients/search`, `GET /patients/{id}/consents` |
| appointment | `POST /appointments`, `GET /appointments/{id}`, `PUT /appointments/{id}`, `GET /availability` |
| queue | `POST /queues`, `GET /queues/{id}`, `POST /queues/{id}/advance` |
| ehr | `POST /encounters`, `POST /clinical-notes`, `GET /patients/{id}/history`, `POST /diagnoses`, `POST /treatments` |
| prescription | `POST /prescriptions`, `GET /prescriptions/{id}`, `POST /prescriptions/{id}/cancel` |
| pharmacy | `GET /medications`, `POST /dispense`, `GET /dispensing/{id}` |
| laboratory | `POST /lab/orders`, `GET /lab/results/{id}`, `PUT /lab/results/{id}/verify` |
| radiology | `POST /imaging-requests`, `GET /studies/{id}`, `POST /reports/{id}/complete` |
| emergency | `POST /emergency/register`, `PUT /emergency/{id}/triage`, `POST /emergency/{id}/activate` |
| surgery | `POST /surgeries`, `PUT /surgeries/{id}/start`, `PUT /surgeries/{id}/complete` |
| bed | `POST /bed-requests`, `PUT /beds/{id}/assign`, `PUT /beds/{id}/release` |
| telemedicine | `POST /telehealth/sessions`, `GET /telehealth/sessions/{id}` |
| billing | `POST /charges`, `POST /invoices`, `POST /payments`, `GET /billing/patients/{id}` |
| insurance | `POST /claims`, `GET /claims/{id}`, `POST /claims/{id}/submit` |
| finance | `GET /journal`, `POST /transactions`, `GET /ledger` |
| inventory | `GET /inventory/items`, `POST /inventory/movements`, `GET /inventory/items/{id}/stock` |
| procurement | `POST /purchase-orders`, `GET /purchase-orders/{id}`, `PUT /purchase-orders/{id}/approve` |
| hr | `GET /employees`, `POST /employees`, `POST /shifts`, `GET /availability` |
| payroll | `POST /payroll/runs`, `GET /payroll/runs/{id}/payslips` |
| reporting | `GET /reports/{type}`, `GET /reports/export` |
| workflow | `POST /workflow/start`, `PUT /workflow/{id}/transition`, `GET /workflow/{id}` |
| ai-gateway | `POST /ai/summarize`, `POST /ai/analyze`, `POST /ai/search`, `POST /ai/document` |

---

# 5. EVENT BUS

## 5.1 Platform

Apache Kafka (3.x, KRaft mode) with Schema Registry (Avro/JSON), Kafka Connect for DB sinks, and Kafka Streams for windowed analytics.

## 5.2 Event Envelope

```json
{
  "eventId": "8d92a1e4-...",
  "eventType": "PatientRegistered",
  "eventVersion": "1.0",
  "timestamp": "2026-08-14T10:00:00Z",
  "source": "patient-service",
  "correlationId": "abc123",
  "userId": "user-0001",
  "payload": { "patientId": "p-100", "facilityId": "f-01" }
}
```

Rules:
- Immutable after publish.
- Versioned — schema evolution never breaks consumers.
- Idempotent consumers — duplicate events must not duplicate state (key by `eventId`).
- **Minimum necessary data** — events carry references (`patientId`) not full records; consumers retrieve via API. Never publish PHI payloads unnecessarily.
- Sensitive events encrypted at rest (Kafka TLS + topic encryption for protected domains).

## 5.3 Topic Naming

`<domain>.<entity>.<action>`

| Domain | Examples |
|---|---|
| `clinical.patient.*` | `clinical.patient.registered`, `clinical.patient.updated`, `clinical.patient.merged` |
| `clinical.appointment.*` | `clinical.appointment.created`, `clinical.appointment.cancelled` |
| `clinical.ehr.*` | `clinical.ehr.encounter-created`, `clinical.ehr.clinical-note-created`, `clinical.ehr.diagnosis-recorded` |
| `clinical.pharmacy.*` | `clinical.pharmacy.medication-dispensed`, `clinical.pharmacy.prescription-created` |
| `clinical.lab.*` | `clinical.lab.order-created`, `clinical.lab.result-available`, `clinical.lab.result-verified` |
| `clinical.radiology.*` | `clinical.radiology.imaging-requested`, `clinical.radiology.report-completed` |
| `clinical.emergency.*` | `clinical.emergency.registered`, `clinical.emergency.activated` |
| `clinical.bed.*` | `clinical.bed.assigned`, `clinical.bed.released` |
| `finance.billing.*` | `finance.billing.charge-created`, `finance.billing.invoice-generated`, `finance.billing.payment-received` |
| `finance.claims.*` | `finance.claims.submitted`, `finance.claims.status-changed` |
| `supply.inventory.*` | `supply.inventory.stock-received`, `supply.inventory.stock-low`, `supply.inventory.stock-consumed` |
| `supply.procurement.*` | `supply.procurement.purchase-requested`, `supply.procurement.purchase-approved` |
| `hr.*` | `hr.employee.created`, `hr.shift.assigned`, `hr.credential.expired` |
| `workflow.*` | `workflow.started`, `workflow.transitioned` |
| `ai.*` | `ai.request.created`, `ai.response.generated`, `ai.prediction.generated`, `ai.model.approved` |
| `audit.*` | consumed by audit-service |

## 5.4 Canonical Workflows (event choreography)

**Medication dispensed:**
```
pharmacy-service → clinical.pharmacy.medication-dispensed
  ├─ inventory-service   → decrement stock → check threshold → StockLow
  ├─ billing-service     → ChargeCreated
  ├─ ehr-service         → patient medication timeline
  ├─ analytics           → consumption metrics
  └─ notification-service→ confirmation to nurse/patient
```

**Patient registered:**
```
patient-service → clinical.patient.registered
  ├─ appointment-service
  ├─ ehr-service  (prepares patient chart)
  ├─ billing-service (opens account ledger)
  ├─ ai prediction-service (risk/flow signals)
  └─ notification-service
```

## 5.5 Reliability

- At-least-once delivery + idempotent handlers.
- Automatic retry with exponential backoff; failures → Dead Letter Queue (`*.dlq`) with alerting.
- Event replay capability for recovery, analytics, and migrations.
- Ordering enforced per partition key (`correlationId` / `patientId`) for critical workflows.
- Retention: audit/clinical long or permanent; operational configurable.
- Consumer lag, DLQ depth, and throughput monitored (Kafka Exporter).

---

# 6. DATABASE ARCHITECTURE

## 6.1 Technology

| Store | Role | Notes |
|---|---|---|
| PostgreSQL 16+ | Primary transactional DB for all services (one schema/set per service) | ACID, JSONB, extensions (pgcrypto, uuid-ossp) |
| Redis 7+ | Cache, sessions, queues, rate-limit counters | Redis Cluster in prod |
| MinIO | Object storage: documents, images, DICOM, audio | S3-compatible, encrypted buckets, versioned |
| Qdrant (or Milvus) | Vector DB: embeddings, knowledge retrieval | Separate network segment |
| OpenSearch (optional) | Full-text clinical and log search | Elk-compatible |

## 6.2 Database-per-Service

```
patient_db  billing_db  inventory_db  hr_db  ehr_db  scheduling_db
 pharmacy_db laboratory_db radiology_db finance_db ai_db  audit_db
```

Naming: `<service>_<env>` (e.g., `patient_prod`). No service ever accesses another service's schema. Cross-service reads happen through APIs or event-echoed, owned projections.

## 6.3 Table Standards

Every business table includes:

```sql
id uuid PRIMARY KEY,
created_at timestamptz NOT NULL DEFAULT now(),
updated_at timestamptz NOT NULL DEFAULT now(),
created_by text,
updated_by text,
version int NOT NULL DEFAULT 1,   -- optimistic locking
status text NOT NULL,
audit_reference text              -- correlation/audit prefilled from header
```

Additional rules:
- CIs: `patient_id`, `medical_record_number`, `full_name`, `date_of_birth`, `gender`, `contact_info`, `emergency_contact`, `registration_date`, `deleted_at/deleted_by/deletion_reason` (soft delete for clinical data).
- Clinical records: **immutable versioning** — never overwrite; new version + amendment + audit record.
- Financial records: no silent deletion; corrections are adjustment entries.
- Migrations: versioned scripts `V001_...sql` (Flyway/Alembic) per service; tested and reversible.
- Indexes justified by query patterns; big tables partitioned (date, facility, department).
- Encryption at rest (AES-256 via pgcrypto + TDE where available), column-level for high-sensitivity PHI (SSN, insurance numbers, consent details).

## 6.4 Audit Database (`audit_db`)

Append-only, tamper-evident (hash chaining + integrity verification), time-synchronized:
`action`, `user_id`, `timestamp`, `service`, `record_id`, `old_value`, `new_value`, `ip_address`, `correlation_id`.

## 6.5 Data Ownership Summary

| Domain | Owned Data |
|---|---|
| patient-service | identities, demographics, contacts, consents, MPI |
| ehr-service | encounters, notes, diagnoses, treatments, vitals |
| pharmacy | medications, prescriptions, dispensing, drug interactions |
| laboratory | orders, samples, results, verification |
| billing | charges, invoices, payments, receipts, taxes |
| inventory | items, lots, expiry, suppliers, warehouses, stock movements |
| hr | employees, departments, shifts, attendance, credentials |
| payroll | payroll runs, payslips, tax records |
| ai | models, prompts, AI request/response audit, embeddings metadata |

## 6.6 Backup & Recovery

- 3-2-1 rule: 3 copies, 2 media types, 1 offline/off-site.
- Daily full + hourly incremental + continuous WAL/PITR; encrypted backups; monthly restore drills.
- RPO/RTO defined per service criticality (clinical/financial near-zero).
- HA: primary + streaming replica (Patroni), failover automation, connection pooling (PGBouncer).

---

# 7. AI ARCHITECTURE

## 7.1 Principles

- 100% local inference. No patient data leaves the facility.
- AI is advisory: suggestions, summaries, predictions, search. Humans approve all clinical/financial actions.
- Every AI call passes authZ (user + role + scope), safety layer, and audit.

## 7.2 Platform Diagram

```
Users (Web/Mobile)
        │
        ▼
   AI Gateway (ai-gateway)
   ┌──────────────────────────────────────────────┐
   │ authZ  │ model routing │ prompt policy │ safety │ rate-limit │ audit │
   └──────────────────────────────────────────────┘
        │
   ┌────┴──────────┬───────────────┬────────────────┐
   ▼               ▼               ▼                ▼
LLM Inference   Embeddings      Speech (Whisper)   OCR (PaddleOCR)
(vLLM/Ollama)   (BGE/E5/Nomic)                     
        │
   ┌────┴──────────────────────┐
   ▼                           ▼
RAG Engine ◄─── Vector DB    Agent Runtime (agent-service)
   │            (Qdrant)     ├─ clinical-documentation-agent
   │                         ├─ pharmacy-agent
   ▼                         ├─ inventory-agent
Knowledge Base                ├─ finance-audit-agent
(guidelines, policies,        ├─ workforce-agent
 protocols, drug data,        └─ command-center-agent
 approved references)     ┌────────────────────────────┐
                          │ Approval Layer (L1–L4)     │
                          │ info → recommend → action  │
                          │ → clinical (human only)     │
                          └────────────────────────────┘
```

## 7.3 Model Strategy

- Foundation models: Llama / Qwen / Mistral / Gemma — selected per workload (multilingual → Qwen; low-resource → Mistral/Gemma; general → Llama).
- Runtime: **vLLM** (production, multi-tenant, GPU optimized) and **Ollama** (dev/small deployments). TensorRT-LLM optional.
- Supporting models: Whisper (speech), PaddleOCR/Tesseract (OCR), BGE/E5/Nomic (embeddings).
- Fine-tuning: prefer **LoRA/QLoRA** on approved, de-identified, governed datasets; start with prompt engineering + RAG before any tuning.
- Model registry with: version, training-data version, eval score, approval status, rollback path. Naming: `HospitalGPT-Clinical-v1.2-approved`.

## 7.4 RAG Pipeline

```
Document → OCR/Text extraction → Cleaning → Chunking → Embedding → Qdrant
Question → Embedding → Vector search → Retrieve top-k → LLM (grounded) → Answer + citations + confidence
```

Knowledge sources: hospital policies, clinical guidelines, protocols, drug information, equipment manuals, approved references. Ownership and access policy per dataset.

## 7.5 AI Agent Rules

- Each agent: defined purpose, limited permissions, approved tools, audit trail, human-approval level.
- Approval levels: **L1** information (no approval) · **L2** recommendation (review) · **L3** action (explicit approval) · **L4** clinical decision (human professional only).
- Agents communicate via APIs + `ai.*` events; agent memory split: session (temp), knowledge (approved), patient-context (authorized only), forbidden (raw uncontrolled PHI).
- AI cannot: diagnose independently, prescribe independently, auto-modify records, auto-approve financial transactions.

## 7.6 AI Audit

Per request: user, model version, input type, output reference, confidence, approval status, timestamp, source citations. Fail-soft: if AI unavailable, all clinical workflows continue normally.

---

# 8. AUTHENTICATION & AUTHORIZATION

## 8.1 Identity Provider

**Keycloak** (self-hosted, offline-capable) — OAuth2, OIDC, SAML, MFA, realm strategy:
- Realm `ehos` with clients: staff-portal (confidential), patient-portal (public), mobile apps, service-clients.
- Identity types: clinical staff, administrative staff, patients, system services, medical devices, AI agents.

## 8.2 Token Model

| Token | Lifetime | Purpose |
|---|---|---|
| Access token (JWT/OIDC) | 5–15 min | Authorize API calls; contains scopes/roles/permissions |
| Refresh token | configurable | Session renewal via `POST /auth/refresh` |
| ID token | short | User claims to frontend |
| Service token (client-credentials) | short | Machine-to-machine |

JWT claims: `user_id`, `name`, `role`, `department`, `permissions[]`, `exp`.

## 8.3 Flows

- **Browsers/mobile:** Authorization Code + PKCE → Keycloak → tokens; MFA enforced for doctors, administrators, finance, IT.
- **Brave/break-glass:** emergency access with reason + full audit + automatic review.
- **Services:** OAuth2 Client Credentials with unique service identity, least privilege.
- **Devices:** X.509 / mTLS certificate identity.
- **AI agents:** dedicated identities with scoped permissions and tool allow-lists.

## 8.4 Authorization

- **RBAC** roles (Doctor, Nurse, Pharmacist, Finance Officer, Administrator, Patient) with permission strings like `patient.read`, `ehr.write`, `prescription.create`, `medication.dispense`, `invoice.read`.
- **ABAC** policies add context: department match, patient assignment, facility, time, data classification, purpose of use.
- Enforcement at every layer: gateway (policy checks), service (fine-grained), database (row-level security where sensitive).

## 8.5 Password & Session Policy

- Password ≥12 chars with complexity; history + expiration.
- Login throttling, lockout, suspicious-login detection.
- Session timeout, device tracking, revocation, concurrent-session control.
- Privileged accounts: MFA + separate accounts + activity monitoring.

---

# 9. API GATEWAY

**Technology:** Kong (recommended) or Envoy/NGINX — deployed as the single external entry point.

Responsibilities:
- TLS termination (TLS 1.3), route `/api/v1/**`, `/fhir/r4/**`, `/ws/**` (WebSocket).
- AuthN: validate Bearer tokens / introspect with Keycloak.
- AuthZ: scope/permission checks at edge; ABAC enrichment.
- Rate limiting (per user, per service, per IP); circuit breaking.
- Request tracing propagation (`X-Request-Id`, `X-Correlation-Id`).
- Response/error normalization; CORS for authorized origins; WAF rules (OWASP).
- Logging of metadata (never bodies of PHI).

Routing topology:
```
CLIENTS (web/mobile/kiosk)
        │
   API GATEWAY  (TLS, routing, authz, rate-limit, WAF)
        │
   ┌────┴───────────────┬──────────────────┬───────────────┐
   ▼                    ▼                  ▼               ▼
Identity Keycloak   Domain Services   AI Gateway        Integrations
   (auth)           (patient, ehr,        (local AI)     (FHIR/HL7/DICOM)
                    lab, billing, ...)
```

---

# 10. DEPLOYMENT ARCHITECTURE

## 10.1 Deployment Tiers

| Tier | Stack | Purpose |
|---|---|---|
| **Local / Dev** | Docker Compose (full stack) | Developer environment, mock AI models |
| **Staging** | Kubernetes (single or small cluster) | Integration, clinical workflow testing |
| **Production** | Kubernetes on-prem (GPU nodes, HA) | Hospital operations; small standalone option: docker-compose single-server |
| **Enterprise** | Multi-cluster, hospital network, DR site | Multi-hospital / network deployment |

## 10.2 Kubernetes Design

- Namespaces: `ehos-system`, `ehos-clinical`, `ehos-finance`, `ehos-ai`, `ehos-integrations`, `ehos-monitoring`, `ehos-security`.
- Workloads: Deployments + StatefulSets (Kafka, PostgreSQL, Qdrant, Redis), HorizontalPodAutoscaler for stateless services; GPU nodes tainted/dedicated for AI.
- Ingress: NGINX/Kong ingress → internal services; mTLS mesh (Istio/Linkerd optional).
- Secrets: HashiCorp Vault + Kubernetes Secrets encrypted at rest; no secrets in Git.

## 10.3 Release Strategy

- Git flow: `main` (prod-ready), `develop`, `feature/*`.
- CI stages: lint → unit tests → security scan (Trivy, SonarQube) → container build → integration tests → (staging) → deploy.
- Zero-downtime: rolling + blue/green; health-gated rollouts; automatic rollback.
- Semantic versioning (`2.4.1`); DB migrations run in pipeline with backup verify.
- AI model pipeline: dataset version → training → eval → security review → model registry → canary deploy → monitor.

## 10.4 Infrastructure as Code

Terraform (infra), Ansible (server config), Helm (k8s charts). Environments: development / testing / staging / production — isolated, no prod data in non-prod.

## 10.5 Hardware Profiles (baseline)

| Scale | Compute | Storage |
|---|---|---|
| Small | 3 application + 2 DB nodes, 1 AI GPU (24GB+) | 5–10 TB SSD |
| Medium | K8s cluster, 4–8 GPU nodes, dedicated DB nodes | 50 TB+ |
| Enterprise | Multi-node cluster + GPU farm + DR site | HA/object/cluster storage |

Backups: 3-2-1, encrypted, immutable; RTO/RPO per service. Offline mode: all critical functions (registration, EHR, pharmacy, billing, ED) run without internet.

---

# 11. MONITORING

Stack (all self-hosted):

| Concern | Tool |
|---|---|
| Metrics | Prometheus (service, DB, Kafka, GPU exporters) |
| Dashboards | Grafana (per-domain + executive hospital dashboard) |
| Logs | Loki (centralized, searchable) |
| Tracing | Tempo (distributed traces, correlation across services) |
| Alerting | Alertmanager (+ page routes, severity levels) |
| Uptime/synthetic | Blackbox exporter on key clinical endpoints |

**Teams of Service Interface (TOIS):**
- Every service exposes `/health`, `/readiness`, `/liveness`.
- Standard metrics: `http_request_duration_seconds`, `http_requests_total`, `service_up`, `kafka_consumer_lag`, `queue_depth`, `ai_inference_latency`, `gpu_utilization`.

**Key alerts:**
- Service down / crash-looping (critical)
- Consumer lag > threshold / DLQ non-empty (critical)
- API latency > p95 budget (warning)
- DB connection saturation / replication lag (critical)
- AI inference latency high / model error rate up (warning)
- Unauthorized access attempts / privilege escalation (security critical)

**Dashboards:** hospital command center (beds, ED load, staffing, inventory, revenue, critical alerts), service health, Kafka health, DB health, GPU/AI usage.

---

# 12. LOGGING

## 12.1 Structured Logging Standard

All services emit JSON structured logs with mandatory fields:

```json
{
  "timestamp": "2026-08-14T10:00:00Z",
  "service": "patient-service",
  "level": "info",
  "requestId": "abc123",
  "correlationId": "corr-7f",
  "userId": "user-0001",
  "operation": "patients.create",
  "result": "success",
  "durationMs": 24
}
```

- **Never log:** passwords, tokens/keys, full medical records, PHI payloads, raw insurance numbers.
- Log levels: debug / info / warn / error / fatal; context-aware sampling in prod.

## 12.2 Pipeline

```
Services (JSON) → Fluent Bit/vector collectors → Kafka log sink → Loki (retention) → Grafana search
  ├─ Promtail/RUO
  └─ Security logs → SIEM (Wazuh/Splunk/Elastic)
```

## 12.3 Audit vs Logs

- **Logs:** operational, short-lived, for debugging/observability.
- **Audit:** immutable, tamper-evident, legally retained, written via `audit-service` to `audit_db` + audit topics. Record: who, what, when, where (IP), which record, old/new values, reason.

---

# 13. SECURITY ZONES & NETWORK

```
Internet ─▶ Firewall ─▶ DMZ (Gateway, patient portal)
               │
      ┌────────┴────────┐
      ▼                 ▼
Application Network   Integrations (FHIR/HL7/DICOM, insurance)
      │
      ▼
Clinical Network (EHR, lab, radiology, pharmacy, medical devices)
      │
      ▼
Database Network (PostgreSQL, Redis, Qdrant)  |  AI Network (GPU, models)
      │
Management / Monitoring / Backup
```

- Default-deny firewall; explicit allow rules reviewed continuously.
- Micro-segmentation across service pods (NetworkPolicies); mTLS within zones.
- Encryption: TLS 1.3 in transit; AES-256 at rest; encrypted backups; dedicated GPU network.
- IDS/IPS + Falco (runtime container security) + SIEM correlation.
- Vulnerability mgmt: continuous scanning, patch SLAs, pentest program.

---

# 14. CROSS-CUTTING STANDARDS

**Testing:** unit (≥80% core), integration (DB + API + events), contract, security (authz, OWASP, pen-test), performance (k6/JMeter), E2E (clinical journeys), AI eval (accuracy/safety/bias/drift), UAT with clinicians. Quality gates before prod.

**CI/CD:** every change must pass lint, tests, security scan, container build, and obtain approval before deploy. Release records + compliance evidence stored.

**Health & reliability:** retries with backoff, idempotency, circuit breakers, graceful degradation (AI optional), dead-letter review workflow, failure drills.

**AI governance:** model approval committee, dataset ownership, safety testing, human-in-the-loop, bias checks, auditability, explainability (sources + confidence).

**API documentation:** OpenAPI per service; event catalog; changelogs; deprecation policy.

---

# 15. IMPLEMENTATION BUILD ORDER

1. **Foundation:** repository skeleton, shared libs, `api-gateway`, `identity-service` (Keycloak), `audit-service`, `configuration-service`, `notification-service`, CI/CD + compose + monitoring baseline.
2. **Patient Platform:** `patient-service`, `appointment-service`, `queue-service`.
3. **Clinical core:** `ehr-service`, `clinical-documentation-service`, `prescription-service`, `workflow-service`.
4. **Operational:** `pharmacy-service`, `laboratory-service`, `radiology-service`, `inventory-service`, `procurement-service`, `billing-service`, `insurance-service`, `finance-service`.
5. **Workforce:** `hr-service`, `payroll-service`, `emergency-service`, `surgery-service`, `bed-service`, `telemedicine-service`.
6. **AI Platform:** `ai-gateway`, `model-service`, `prompt-service`, `embedding-service`, `rag-service`, `knowledge-service`, `speech-service`, `ocr-service`, `agent-service`, `prediction-service`, `executive-ai-service`.
7. **Interfaces & Reporting:** frontend portals, mobile apps, `reporting-service`, executive dashboard, integrations (FHIR/HL7/DICOM).
8. **Hardening:** penetration test, performance test, DR simulation, compliance validation.

Each phase ends only when: code + tests + Dockerfile + OpenAPI + README + events + migration pass quality gates.

---

# FINAL PRINCIPLE

> EHOS is a connected healthcare intelligence platform. Every architectural decision must improve patient safety, strengthen security, simplify maintenance, and enable intelligent healthcare without compromising privacy or reliability.

**Architecture is complete. Awaiting instruction to begin implementation (Phase 0 / Foundation).**