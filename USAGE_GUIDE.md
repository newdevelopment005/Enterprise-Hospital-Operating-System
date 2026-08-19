# EHOS — How to Use the System

A practical walkthrough of the Enterprise Hospital Operating System, from the
frontend apps down to each microservice. It assumes the stack is running
(see `INSTALLATION_AND_USAGE.md` — `make up`, or run services locally) and that
you have opened `.env` with real values.

Two networks exist:

- **Dev / direct**: each service listens on its own port and (except
  `ai-service`) does **not** require a token. Fast for exploring.
- **Production-shaped / via the gateway**: `http://localhost:8000` validates a
  Keycloak-issued JWT on every protected route. Use this path with `Bearer`
  tokens (§2).

All services also expose interactive OpenAPI docs at
`http://localhost:<port>/docs` — the fastest way to explore every endpoint.

---

## 1. What you are driving

| Layer | Component | URL / Port |
|---|---|---|
| Frontend | patient-registration | http://localhost:5173 |
| Frontend | ehr-portal | http://localhost:5174 |
| Frontend | ai-assistant (HospitalGPT) | http://localhost:5175 |
| Frontend | executive-dashboard | http://localhost:5176 |
| Gateway | api-gateway | http://localhost:8000 |
| IAM | Keycloak console (`admin`) | http://localhost:8400 `/admin` |
| Backend | authentication | http://localhost:8500 |
| Backend | patient (MPI) | http://localhost:8501 |
| Backend | ehr (clinical record) | http://localhost:8502 |
| Backend | knowledge (RAG) | http://localhost:8505 |
| Backend | ai (HospitalGPT) | http://localhost:8506 |
| Backend | prediction | http://localhost:8507 |
| Backend | audit | http://localhost:8200 |
| Backend | configuration | http://localhost:8100 |
| Backend | notification | http://localhost:8300 |

Run a frontend app locally:

```bash
cd frontend/apps/patient-registration   # or ehr-portal / ai-assistant / executive-dashboard
npm install
npm run dev                             # serves on 5173; proxies /api to its service
```

---

## 2. Authentication (Keycloak tokens for the gateway)

Gateway-protected routes need a token issued by the `ehos` realm. Get one with
the password grant (use the admin user imported from
`backend/identity-service/keycloak/realm-ehos.json`; password =
`KEYCLOAK_ADMIN_PASSWORD`, default `change-me`):

```bash
curl -s -X POST http://localhost:8400/realms/ehos/protocol/openid-connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "client_id=ehos-api" \
  -d "client_secret=<YOUR_KEYCLOAK_CLIENT_SECRET>" \
  -d "username=admin" \
  -d "password=<KEYCLOAK_ADMIN_PASSWORD>" \
  -d "scope=openid"
```

Response contains `access_token` (JWT) — use it as
`-H "Authorization: Bearer <access_token>"` on every gateway call below.

> **The in-repo IAM (`authentication-service`, §3) issues its own JWTs.** Those
> tokens are *not* signed by Keycloak, so the gateway rejects them with 401
> (see the identity-path design note in `INSTALLATION_AND_USAGE.md` §9). For
> development convenience, all of the walkthroughs below also work **direct** at
> the service's own port — no token required, except `ai-service` which fails
> closed (401) without a valid Keycloak token.

---

## 3. Identity: register a user, log in, enable MFA

The `authentication-service` is EHOS's own IAM (self-service registration,
sessions, TOTP MFA, lockout, tokens). Hit it directly at :8500.

**Register** (a strong password is enforced — ≥12 chars with upper/lower/digit/special):

```bash
curl -s -X POST http://localhost:8500/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"dr.amina","email":"dr.amina@ehos.example","password":"Am1na!Passw0rd","full_name":"Dr Am. Mina"}'
```

**Login** (no MFA enrolled yet → returns tokens directly):

```bash
curl -s -X POST http://localhost:8500/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"dr.amina","password":"Am1na!Passw0rd"}'
```

**Enroll MFA** (get the `otpauth_uri`, scan into an authenticator app):

```bash
curl -s -X POST http://localhost:8500/api/v1/auth/mfa/enroll -H "Content-Type: application/json" -d '{}'
```

**Confirm + verify**: after confirming enrollment
(`POST /auth/mfa/confirm` with the 6-digit code), login responses carry
`mfa_required: true`; complete with `POST /auth/mfa/verify` + the TOTP code.

Other identity endpoints: `/refresh`, `/logout`, `/sessions`, `/me`,
`/me/password`, `/users` (admin), `/roles` + `/permissions` (RBAC),
`/abac/check` (attribute-based access decisions), `/policy/password`.

---

## 4. Patient registration and MPI (patient-service, :8501)

**Register a patient:**

```bash
curl -s -X POST http://localhost:8501/api/v1/patients \
  -H "Content-Type: application/json" \
  -d '{
    "first_name":"Amina","last_name":"Mwangi","date_of_birth":"1990-04-22",
    "gender":"FEMALE","nationality":"TZ","blood_group":"O+","language_pref":"en",
    "national_identifier":"12345678901234",
    "contacts":[{"name":"Amina Mwangi","relationship":"SELF","phone":"+255712345678"}],
    "addresses":[{"line1":"10 Upanga Rd","city":"Dar es Salaam","country":"TZ","is_primary":true}],
    "emergency_contact":{"name":"John Mwangi","relationship":"SPOUSE","phone":"+255700112233"}
  }'
```

Response includes `id` (patientId), `patient_number` and `mrn`.

**Search / view / update:**

```bash
curl -s "http://localhost:8501/api/v1/patients?q=Mwangi&limit=10"
curl -s http://localhost:8501/api/v1/patients/<patient_id>
curl -s -X PATCH http://localhost:8501/api/v1/patients/<patient_id> \
  -H "Content-Type: application/json" -d '{"marital_status":"MARRIED","nationality":"TZ"}'
```

**Add record parts:** `/{id}/alerts`, `/{id}/biometrics`, `/{id}/photo` (base64),
`/{id}/insurance`, `/{id}/identifiers`, `/{id}/emergency-contact`, and
`/{id}/timeline` to replay the patient's activity. The clinical record (*not*
demographics) lives in the ehr-service — see §5.

**Merge duplicates (MPI):**

```bash
curl -s -X POST http://localhost:8501/api/v1/patients/merge \
  -H "Content-Type: application/json" \
  -d '{"survivor_id":"<id>","duplicate_id":"<id>"}'
```

Every registration/update emits a canonical event on `clinical.patient.*`
(subscribed by audit + notification).

---

## 5. Clinical record (ehr-service, :8502)

All clinical resources hang off `/api/v1/ehr/patients/{patient_id}/...`.

**Open an encounter, then write data into it:**

```bash
curl -s -X POST http://localhost:8502/api/v1/ehr/patients/<patient_id>/encounters \
  -H "Content-Type: application/json" \
  -d '{"encounter_type":"OUTPATIENT","reason":"Fever and headache for 2 days"}'
# -> returns encounter_id

curl -s -X POST http://localhost:8502/api/v1/ehr/patients/<patient_id>/vitals \
  -H "Content-Type: application/json" \
  -d '{"vital_type":"TEMP","value_numeric":38.4,"unit":"C","encounter_id":"<encounter_id>"}'
# vital_type is one of BP|HR|RR|TEMP|SPO2|WEIGHT|HEIGHT|BMI|GLUCOSE|PAIN|GCS
```

**SOAP note (then sign it — signing is immutable):**

```bash
curl -s -X POST http://localhost:8502/api/v1/ehr/patients/<patient_id>/soap \
  -H "Content-Type: application/json" \
  -d '{"author_id":"<user_id>","encounter_id":"<encounter_id>",
       "subjective":"Fever, malaise 2 days","objective":"T 38.4C, pharynx red",
       "assessment":"Viral upper respiratory infection","plan":"Hydration, paracetamol PRN"}'
curl -s -X POST "http://localhost:8502/api/v1/ehr/patients/<patient_id>/notes/<note_id>/sign?signed_by=<user_id>"
```

**Other clinical objects:** `progress-notes`, `discharge-summary`,
`diagnoses` (ICD-10, `/{id}/resolve`), `medications`, `orders` (`PATCH` to
alter status), `allergies`, `problems`, `medical-history`.

**Reads:** `notes`, `diagnoses`, `medications`, `orders`, `allergies`,
`problems`, `medical-history`, `timeline` (clinical view), and `chart`
(rendered vitals/labs picture).

Signed/amended notes keep verifiable versions:
`notes/{note_id}/versions`, `notes/{note_id}/amendments`.

---

## 6. Knowledge base & RAG (knowledge-service, :8505)

**Bootstrap the offline corpora, then query:**

```bash
curl -s -X POST http://localhost:8505/api/v1/knowledge/seed-defaults -H "Content-Type: application/json" -d '{}'
curl -s http://localhost:8505/api/v1/knowledge/corpora
```

**Ingest a document** (auto-chunked, embedded, searchable):

```bash
curl -s -X POST http://localhost:8505/api/v1/knowledge/ingest \
  -H "Content-Type: application/json" \
  -d '{"doc_type":"SOP","title":"Paracetamol Dosing Guideline",
       "content":"Adults: 500mg-1g every 4-6 hours, max 4g/24h. ...",
       "approved_by":"am.ina"}'
```

**Semantic search** (uses your Ollama embedder — `EMBEDDING_ADAPTER=ollama`,
`EMBEDDING_MODEL=all-minilm:l6-v2`):

```bash
curl -s -X POST http://localhost:8505/api/v1/knowledge/search \
  -H "Content-Type: application/json" \
  -d '{"query":"max daily paracetamol dose","top_k":5}'
```

**Try the embed endpoint directly:**
`POST /api/v1/knowledge/embed` with `{"text":"..."}` returns the vector +
`model`. Documents → `documents`, `documents/{id}/chunks`,
`documents/{id}/status` (review/approval lifecycle).

---

## 7. HospitalGPT (ai-service, :8506)

**Get runtime status (proves the adapter wiring):**

```bash
curl -s http://localhost:8506/api/v1/ai/status
curl -s -H "Authorization: Bearer <KEYCLOAK_TOKEN>" http://localhost:8506/api/v1/ai/status
```

> Every `ai-service` endpoint requires a valid bearer token (Keycloak JWKS,
> fail-closed). Get one as in §2.

**Chat with local RAG:**

```bash
curl -s -X POST http://localhost:8506/api/v1/ai/chat \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"message":"What is the max daily paracetamol dose?","use_rag":true}'
```

`chat` returns the grounded answer, sources, and a `request_id`. If the request
needs human approval, it lands in `requests` — approve via
`POST /api/v1/ai/requests/{request_id}/approve`.

**Conversations & memory** (`user_id` is taken from the token subject):
`POST /conversations`, `GET /conversations/{id}/messages`,
`GET /memories`, `PUT /memories` (store a fact), `DELETE /memories/{id}`.
**Feedback:** `POST /feedback` (`ai_request_id`, `rating` 1-5).
**Media facades:** `POST /stt` (audio→text), `/tts` (text→base64 audio),
`/ocr` (image→text) — adapters `mock` or `http`.

**Model & prompt manager:** `GET/POST /models`, `/models/{key}/load`,
`/models/{key}/unload`, `GET/POST /prompts`. Register your installed Ollama model:

```bash
curl -s -X POST http://localhost:8506/api/v1/ai/models \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"model_key":"gemma2:2b","family":"LLM","base_name":"Gemma","version":"2-2b","context_window":8192}'
```

**Agents:** `GET /agents`, `POST /agents/{key}/run` (`{"goal":"...","context":{}}`),
`GET /agent-runs`, `GET /agent-runs/{run_id}/actions`, and approve pending
actions via `POST /agent-actions/{action_id}/approve`.

---

## 8. Predictions & operations (prediction-service, :8507)

**See the target catalog, train/approve a model, generate a forecast:**

```bash
curl -s http://localhost:8507/api/v1/predictions/targets

curl -s -X POST http://localhost:8507/api/v1/predictions/models/train \
  -H "Content-Type: application/json" \
  -d '{"target":"bed-occupancy","entity_type":"ward","entity_id":"cardiology","series":[42,45,41,47,50,49,53],"approve":true}'

curl -s -X POST http://localhost:8507/api/v1/predictions/generate \
  -H "Content-Type: application/json" \
  -d '{"entity_type":"ward","entity_id":"cardiology","series":[42,45,41,47,50,49,53],"horizon_steps":7}'
```

**Governance:** `POST /models/{model_key}/approve|/reject` (human-in-the-loop);
`GET /models`, `GET /models/{key}`; **reconciling** against actuals:
`POST /reconcile` (`prediction_key`, `series`). Look up any forecast with
`GET /lookup/{prediction_key}`. All offline (local adapters only).

---

## 9. Notifications (notification-service, :8300)

**Templates and ad-hoc sends:**

```bash
curl -s -X POST http://localhost:8300/api/v1/templates \
  -H "Content-Type: application/json" \
  -d '{"template_key":"lab_result_ready","channel":"email",
       "subject":"Lab result ready","body_template":"Dear {{name}}, your result is ready."}'

curl -s -X POST http://localhost:8300/api/v1/send \
  -H "Content-Type: application/json" \
  -d '{"template_key":"lab_result_ready","recipient":"dr.amina@ehos.example",
       "channel":"email","variables":{"name":"Dr Mina"}}'
```

With the default `NOTIFICATIONS_TRANSPORT=log`, delivery is simulated (a mocked
id + a log line). Set `smtp` or `http` (§5.11 of the install guide) for real
delivery. The consumer also auto-sends templates for subscribed `clinical.*`
events.

---

## 10. Audit trail & integrity (audit-service, :8200)

```bash
curl -s "http://localhost:8200/api/v1/records?limit=10"     # latest records
curl -s http://localhost:8200/api/v1/records/<record_id>    # one record
curl -s http://localhost:8200/api/v1/integrity              # chain verification
```

`/integrity` verifies the hash chain — a `"chain_valid": true` response proves
no record was tampered with. Every event from `auth.topic`, `audit.topic` and
the registry topics is mirrored here.

---

## 11. Feature flags & reference config (configuration-service, :8100)

```bash
curl -s http://localhost:8100/api/v1/all                       # full snapshot
curl -s http://localhost:8100/api/v1/flags                     # feature flags
curl -s -X POST http://localhost:8100/api/v1/flags -H "Content-Type: application/json" \
  -d '{"name":"telehealth.enabled","enabled":false}'
curl -s http://localhost:8100/api/v1/entries/<config_key>      # one config entry
```

Changes emit `ConfigurationUpdated` on `configuration.topic`.

---

## 12. A complete day-in-the-life scenario

1. `make up` (or local services). Open the `patient-registration` app at
   http://localhost:5173 and register a patient.
2. Open the **ehr-portal** (http://localhost:5174), open an OUTPATIENT
   encounter for that patient, record vitals, write and sign a SOAP note, add a
   diagnosis and a medication.
3. In the **knowledge-service**, `seed-defaults`, ingest a dosing guideline,
   and search it.
4. In **HospitalGPT** (ai-assistant at :5175, needs a Keycloak token), ask a
   question about that guideline — the `chat` reply cites the ingested,
   approved document.
5. In the **prediction-service**, train/approve a bed-occupancy model and
   generate a 7-day forecast; confirm it reconciles against actuals later.
6. Send a lab-result email via **notification-service**; check the delivery
   was logged.
7. In the **executive-dashboard** (http://localhost:5176) review the forecast
   and AI insights.
8. Prove accountability: `GET /api/v1/records` and `/api/v1/integrity` on the
   audit-service show every step above recorded in a verified chain.

## 13. Common gotchas

- **401 from the gateway / ai-service**: you need a **Keycloak**-issued token,
  not an authentication-service token (§2 note). Refresh it when it expires
  (default 15 min).
- **`RUNTIME_UNAVAILABLE` / 404 in ai/status**: the configured model isn't
  installed in Ollama — use an installed one (`gemma2:2b`, `tinyllama:1.1b`) or
  `INFERENCE_ADAPTER=mock`.
- **Embedding errors in knowledge-service**: `EMBEDDING_ADAPTER=ollama` needs an
  embedding model (`all-minilm:l6-v2`); completion-only models can't embed.
- **`POSTGRES_PASSWORD must be set...`**: `EHOS_ENV` isn't `development` and
  you left the default password.
- **Server 500 responses**: check `docker compose logs <service>`; every handler
  returns the standard envelope `{"success", "data", "timestamp"}` and errors
  carry a short error code.