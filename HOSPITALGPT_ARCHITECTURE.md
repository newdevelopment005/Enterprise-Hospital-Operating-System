# HOSPITALGPT — EHOS Local AI Platform Architecture

**Version:** 1.0.0
**Document Type:** Local Healthcare AI Platform Architecture
**Audience:** AI Engineers, Software Architects, Clinical Informatics, Security

---

## 1. Purpose

HospitalGPT is the **fully offline** AI assistant layer of EHOS. It runs entirely
inside the hospital network, uses **no OpenAI or cloud APIs**, and answers **only
from local knowledge**.

It is governed by:
- `AI_AGENT_ARCHITECTURE.md` (multi-agent standard, human-in-the-loop)
- `AI Behaviour & Operational Policy Standard.md` (local-only, truthfulness, forbidden practices)
- `DATABASE_DESIGN.md` (sections 8.1 ai_db, 8.2 knowledge_db, 10 cross-cutting)
- `API_DESIGN_STANDARD.md` (EHOS envelope `{success, data, statusCode}`)

---

## 2. Non-Negotiables (Hard Constraints)

1. **Zero external calls.** No OpenAI, Anthropic, Google, HuggingFace-download at
   runtime. All model traffic is `localhost` HTTP to a local runtime.
2. **Local model families only:** Llama (e.g. `llama3.1`), Qwen (`qwen2.5`),
   Mistral (`mistral`), Gemma (`gemma2`). Served by Ollama or llama.cpp on-prem.
3. **RAG-grounded answers.** Every answer restates retrieved local chunks with
   `sources`; if nothing is retrieved the assistant says
   *"I do not have enough verified information to answer this safely."*
4. **Human authority.** AI never makes final diagnoses, never prescribes, never
   modifies clinical records. Action levels 1-4 per AI_AGENT_ARCHITECTURE §19.
5. **Append-only audit.** Every AI interaction is written to `ai_requests`
   (immutable) and retrievals to `knowledge_access_log`.
6. **Permission + approval gates** via `ai_request_approvals`.

---

## 3. Component Map (requested -> implementation)

| Requested component | Implementation |
|---|---|
| AI Gateway          | `ai-service` route layer + `AiRequestGateway` (audit log, approval gate, request_id) |
| Model Manager       | `ModelManager` over `ai_models` + `ai_model_loads` (registry, approval, runtime slots) |
| Inference Engine    | `InferenceEngine` — pluggable adapters: `ollama`, `llamacpp`, `mock` (offline only) |
| Prompt Manager      | `PromptManager` over `prompt_templates` (versioned, VARS render, safety rules) |
| Memory Manager      | `MemoryManager` — short-term (conversations/messages) + long-term (`ai_memories`) |
| Vector Database     | `knowledge_db.document_chunks` + `VectorStore` (pgvector-ready, pure-python cosine fallback) |
| Embedding Engine    | `EmbeddingEngine` — pluggable adapters: `ollama`, `mock` (deterministic local) |
| Speech-to-Text      | `SttEngine` — adapter (`mock`, local whisper/Ollama backend placeholder) |
| Text-to-Speech      | `TtsEngine` — adapter (`mock` WAV, local backend placeholder) |
| OCR                 | `OcrEngine` — adapter (`mock`, local tesseract backend placeholder) |
| Medical RAG         | `RagService` in `knowledge-service` + retrieval bridge in `ai-service` |
| Clinical Guidelines | knowledge corpus `GUIDELINE` |
| Hospital Policies   | knowledge corpus `POLICY` |
| Medication Database | knowledge corpus `MEDICATION` |
| Laboratory Reference| knowledge corpus `LAB_REFERENCE` |

---

## 4. Services

### 4.1 `knowledge-service` (port 8505) — owns `ehos_knowledge` DB
**Responsibilities:** versioned knowledge documents, document loaders (PDF/Word/
Markdown/Hospital SOP/Drug Formulary/Books/Journals), chunking, embeddings,
vector retrieval, access audit, corpus seed data. Extended by
`MEDICAL_KNOWLEDGE_BASE.md`.

Paths (`/api/v1/knowledge/...`):
- `POST /ingest` — multipart file upload → loader → chunk/embed (`doc_type`, `kind`, `title`, `auto_approve`)
- `POST /documents` — upsert a titled document (content is chunked + embedded)
- `GET /documents` / `GET /documents/{id}` / `PATCH /documents/{id}` / `DELETE`
- `GET /documents/{id}/chunks`
- `POST /search` — `{query, doc_type?, top_k}` → ranked chunks with scores + doc meta
- `POST /embed` — embed arbitrary text (used by ai-service for its own keys)
- `POST /seed-defaults` — load the four bootstrapped local corpora (guidelines/policies/medications/lab reference)

### 4.2 `ai-service` (port 8506) — owns `ehos_ai` DB
**Responsibilities:** AI Gateway, model registry/loads, inference, prompts,
conversation memory, chat orchestration, STT/TTS/OCR facade, feedback.

Paths (`/api/v1/ai/...`):
- `POST /chat` — RAG chat `{conversation_id?, message, model_key?, use_rag?}`
- `POST /conversations` / `GET /conversations/{id}/messages`
- `GET /models` / `POST /models/{key}/load` / `POST /models/{key}/unload`
- `GET /prompts` / `POST /prompts` / `GET /prompts/{id}`
- `GET /memories` / `PUT /memories` / `DELETE /memories/{id}`
- `POST /stt` / `POST /tts` / `POST /ocr` (multipart; engine via adapter)
- `POST /requests/{id}/approve` — human approval gate
- `POST /feedback` — 1..5 rating linked to `ai_request_id`
- `GET /status` — runtime/capability status for the UI

### 4.3 Runtime binding (adapter pattern)
```
Inference/Embedding adapters
 ├─ mock      : deterministic, no network, used for tests/dev (always available)
 ├─ ollama    : http://localhost:11434  (offline local runtime)
 └─ llamacpp  : http://localhost:8080   (llama.cpp server)
```
Selection via `AI_INFERENCE_ADAPTER`, `AI_EMBEDDING_ADAPTER`,
`OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `AI_LLAMACPP_URL`. If the configured local
runtime is unreachable the engine returns a `503`-style `AiError`
(`RUNTIME_UNAVAILABLE`), never a fake cloud call.

---

## 5. Chat Data Flow (RAG)

```
User
 → ai-service POST /chat
 → MemoryManager.load(conversation)         (short-term turns)
 → RagService.retrieve(query)               (→ knowledge-service /search)
 → PromptManager.render(rag_template, {conversation, context, query})
 → InferenceEngine.generate(prompt, model_key)
 → AiRequestGateway: create ai_requests (immutable) + latency + tokens
 → MemoryManager.append(conversation, user+assistant)
 → Response {answer, sources[], request_id}
```

## 6. Approval Levels (per AI_AGENT_ARCHITECTURE §19)
| Level | Meaning | Representative request_type |
|---|---|---|
| 1 | Information (no approval) | SEARCH, SUMMARIZE, DOCUMENT |
| 2 | Recommendation (human review) | ANALYZE, PREDICT |
| 3 | Action (explicit approval) | AGENT (proposed action) |
| 4 | Clinical decision (human only) | TRANSCRIBE→note drafted, never auto-saved |

Chat maps to level 1-2 by `request_type`; the `ai_requests.approval_status`
gate and `ai_request_approvals` implement it.

---

## 7. Database Migrations
- `database/ai_db/V001__init.sql` — registry, requests, prompts, agents, predictions, evaluations, feedback (existing)
- `database/ai_db/V002__hospitalgpt.sql` — **new**: `ai_conversations`, `ai_messages`, `ai_memories`, `ai_model_loads`
- `database/knowledge_db/V001__init.sql` — documents, chunks, access log (existing)
- `database/knowledge_db/V002__rag_corpora.sql` — **new**: doc_type extension (+MEDICATION, +LAB_REFERENCE), chunk vectors, corpus tables

---

## 8. Security
- No external egress from these services (network policy blocks WAN).
- `ai_requests` is append-only (no update, no soft delete).
- Retrieval always audited in `knowledge_access_log`.
- Memory stores prompts + answers only; never full raw clinical records
  (Forbidden Memory per AI_AGENT_ARCHITECTURE §16).
- Prompt injection hardening via `PromptManager.safety_rules` and response
  refusal template from the AI Behaviour policy.

---

## 9. Verification
- Both services: `ruff check .`, `pytest` (in-memory sqlite, mock adapters).
- Both V002 migrations compile (`py_compile`); applied via `database/apply.py`.
- Frontend `ai-assistant`: `tsc -b` + `vite build` (proxy 5175 → 8506).
- Frontend `executive-dashboard`: `tsc -b` + `vite build` (proxy 5176 → 8507 forecasts, 8506 AI insights).

---

## 10. Repo Layout Added
```
backend/ai-service/        # AI Gateway + managers + engines + chat
backend/knowledge-service/ # RAG knowledge base + vectors + corpora
frontend/apps/ai-assistant/# chat UI
database/ai_db/V002__hospitalgpt.sql
database/knowledge_db/V002__rag_corpora.sql
```