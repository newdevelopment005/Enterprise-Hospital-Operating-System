# ai-service (HospitalGPT)

The **ai-service** is the HospitalGPT brain: fully offline AI Gateway, Model Manager,
Inference Engine, Prompt Manager, Memory Manager, RAG bridge and STT/TTS/OCR facades.
It owns the `ehos_ai` database and **never calls any external/cloud service** — all model
traffic is to local runtimes (Ollama / llama.cpp) on `localhost`.

## Features
- **AI Gateway**: append-only `ai_requests` audit log, human-in-the-loop approvals (levels 1-4)
- **Model Manager**: registry (`ai_models`) + live load state (`ai_model_loads`); defaults for Llama, Qwen, Mistral, Gemma
- **Inference Engine**: adapters `mock` (deterministic offline), `ollama`, `llamacpp`
- **Prompt Manager**: versioned `prompt_templates` incl. HF-locked hospitalgpt_system prompt
- **Memory Manager**: short-term conversation memory (`ai_conversations`/`ai_messages`), long-term `ai_memories`
- **Embedding / RAG bridge**: queries the knowledge-service for retrieved sources; answer is grounded in them or refuses
- **STT / TTS / OCR**: offline facade endpoints (mock adapters; local engines swappable)
- **Feedback**: 1–5 rating linked to each `ai_request_id`

## API (`/api/v1/ai`)
| Method | Path | Purpose |
|---|---|---|
| POST | `/chat` | RAG-grounded chat |
| GET/POST | `/conversations` | conversation memory |
| GET | `/conversations/{id}/messages` | message history |
| GET/POST | `/models` | registry |
| POST | `/models/{key}/load` · `/unload` | live load control |
| GET/POST | `/prompts` | prompt templates |
| GET/PUT/DELETE | `/memories` | long-term memory |
| GET | `/requests/{id}` · POST `/requests/{id}/approve` | audit + approvals |
| POST | `/feedback` | rating |
| POST | `/stt` `/tts` `/ocr` | media facades |
| GET | `/status` | runtime/capability status |

## Run
```bash
pip install -e ".[test]"
uvicorn ai_service.main:app --port 8506
```
OpenAPI: `/docs`; spec checked into `openapi.yaml`.

## Verify
```bash
python -m ruff check .
python -m pytest
# 14 tests (mock adapters, in-memory SQLite)
```

## Environment
- `AI_INFERENCE_ADAPTER` = `mock` | `ollama` | `llamacpp`
- `AI_EMBEDDING_ADAPTER` = `mock` | `ollama`
- `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_EMBEDDING_MODEL`
- `AI_LLAMACPP_URL`
- `AI_KNOWLEDGE_SERVICE_URL` (default `http://localhost:8505`)

## Database
`database/ai_db/V001__init.sql` + `V002__hospitalgpt.sql` (conversations, messages, memories, model loads, CHAT/TTS enums).
Applied via `python database/apply.py --only ai_db`. See `HOSPITALGPT_ARCHITECTURE.md` for the full design.