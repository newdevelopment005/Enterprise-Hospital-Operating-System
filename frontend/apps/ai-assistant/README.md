# ai-assistant

HospitalGPT chat UI for EHOS — a Vite + React + TypeScript app talking to the
**ai-service** (`http://localhost:8506`) via the standard `/api` dev proxy (port 5175).

Fully offline: shows the runtime adapter (mock/ollama/llamacpp), lets you pick the
local model (Llama / Qwen / Mistral / Gemma), toggles RAG grounding, cites retrieved
sources, sends feedback (1–5) to the audit-linked `ai_request_id`, and exposes the
STT / TTS / OCR facades.

## Dev
```bash
npm install
npm run dev          # http://localhost:5175
```

## Build & typecheck
```bash
node node_modules/typescript/bin/tsc -b
node node_modules/vite/bin/vite.js build
```

## Layout
- `src/lib/client.ts` — typed REST client (envelope-aware)
- `src/lib/types.ts` — DTO types (snake_case)
- `src/components/ChatPanel.tsx` — chat, model picker, RAG toggle, sources, feedback
- `src/components/MediaPanel.tsx` — mic dictation (STT), TTS playback, OCR upload

NOTE: if you see `shellcheck.exe` errors from npm scripts, run the tsc/vite binaries
directly as above (the machine's global npm `shell` config points at shellcheck).