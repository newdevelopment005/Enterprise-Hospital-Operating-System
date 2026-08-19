# knowledge-service

EHOS local **RAG knowledge base / Medical Knowledge Base** for HospitalGPT — owns the `ehos_knowledge` database.

Fully offline: documents are chunked, embedded and searched with **no external calls**.
Vectors live as JSONB float arrays (pgvector-ready); cosine similarity is computed locally.

## Features
- Document loaders: **PDF, Word (.docx), Markdown/Text, Hospital SOP (JSON),
  Drug Formulary (CSV/JSON), Medical Books (per-chapter), Medical Journals (per-article)**
- Versioned knowledge documents (Clinical Guidelines, Hospital Policies, Medication DB,
  Laboratory Reference, Protocols, Formulary, Books, Journals, …)
- Chunking + local embedding (adapter: `mock` default, `ollama` for real offline embeddings)
- Vector retrieval with `sources` + scores + access audit log
- Corpus catalog and one-shot seed of the four default corpora

## API (`/api/v1/knowledge`)
| Method | Path | Purpose |
|---|---|---|
| POST | `/ingest` | multipart file upload → loader → chunk/embed (doc_type, kind, title, auto_approve) |
| POST | `/documents` | ingest raw text (existing) |
| GET | `/documents[?doc_type]` | list documents |
| GET | `/documents/{id}` | get one |
| GET | `/documents/{id}/chunks` | list chunks |
| PATCH | `/documents/{id}/status` | PENDING/INDEXED/APPROVED/… |
| DELETE | `/documents/{id}` | retire a document |
| POST | `/search` | RAG retrieval |
| POST | `/embed` | embed arbitrary text |
| GET | `/corpora` | corpus catalog |
| POST | `/seed-defaults` | load the four default corpora |

### Ingest kinds
| `kind` | File | doc_type(s) |
|---|---|---|
| (auto via extension) | `.pdf` `.docx` `.txt` `.md` `.csv` `.book.json` `.journal.json` | rule above |
| `sop` | SOP JSON | `PROTOCOL` |
| `formulary` | drug CSV/JSON | `MEDICATION` (`FORMULARY`) |
| `book` | book JSON | `TEXTBOOK` |
| `journal` | journal JSON | `JOURNAL` |

JSON files are ambiguous, so they require `kind` (or `doc_type` `FORMULARY`/`MEDICATION` for `.json`).

## Run
```bash
pip install -e ".[test]"
uvicorn knowledge_service.main:app --port 8505
```
OpenAPI: `docs` → `/docs`; spec also checked into `openapi.yaml`.

## Verify
```bash
python -m ruff check .
python -m pytest
# 30 tests (in-memory SQLite + mock embeddings; real PDF/DOCX fixtures)
```

## Loader dependencies
Binary loaders import their parser lazily: `pip install -e ".[loaders]"`
(or `.[test]`) installs `pypdf` (PDF) and `python-docx` (Word). Without them the
service still runs — PDF/Word ingestion returns `LOADER_UNAVAILABLE` (503).

## Environment
- `AI_EMBEDDING_ADAPTER` = `mock` | `ollama`
- `OLLAMA_BASE_URL`, `OLLAMA_EMBEDDING_MODEL` (e.g. `nomic-embed-text`)
- `MAX_UPLOAD_BYTES` (default 20 MiB), `PDF_MAX_PAGES` (default 500)
- POSTGRES_*/EHOS_ vars from `ehos-common`

## Database
`database/knowledge_db/V001__init.sql`, `V002__rag_corpora.sql`,
`V003__medical_knowledge.sql` (JOURNAL doc_type + `source_format`/`ingestion_ref`
provenance). Applied via `python database/apply.py --only knowledge_db`.
See `MEDICAL_KNOWLEDGE_BASE.md` for the full design.