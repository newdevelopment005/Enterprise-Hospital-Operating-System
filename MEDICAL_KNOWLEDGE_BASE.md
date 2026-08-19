# MEDICAL_KNOWLEDGE_BASE.md

# Enterprise Hospital Operating System (EHOS)

# Medical Knowledge Base Architecture

**Version:** 1.0.0
**Document Type:** Medical AI Knowledge Base Design
**Audience:** AI Engineers, Clinical Informatics, Knowledge Managers, Integration Architects

---

## 1. Purpose

The Medical Knowledge Base is the **source of truth for the AI layer**: every
claim the HospitalGPT agents make must be grounded in ingested, versioned,
searchable medical documents. It runs on the existing `knowledge-service`
(`ehos_knowledge`, port 8505) and extends it with a **document ingestion
pipeline**: upload → loader → extract → chunk → embed → vector search.

This document is the design contract; the accompanying implementation adds the
loaders, ingestion API and search surface described here.

### Extends
- `HOSPITALGPT_ARCHITECTURE.md` — RAG tier, corpora, adapters
- `SPECIALIZED_AI_AGENTS_ARCHITECTURE.md` — knowledge sources per agent
- `DATABASE_DESIGN.md` §8.2 — `ehos_knowledge` schema
- `EVENT_BUS_SCHEMAS.md` — ingestion/audit event conventions

---

## 2. Non-Negotiables

1. **Offline only.** Parsers and embeddings run locally; no cloud OCR/parsing.
2. **Provenance.** Every document records `source_format` (PDF/DOCX/SOP/...),
   `ingestion_ref` (file URI) and content hash.
3. **Versioning.** Re-ingesting a title creates a new `version`; old versions
   stay searchable until approved retirement.
4. **Human approval.** Ingested documents start `PENDING` → `INDEXED` →
   `APPROVED`; only `INDEXED`/`APPROVED` documents return in search.
5. **Audit.** Every retrieval is written to `knowledge_access_log`; nothing is
   unlogged.
6. **No PHI.** Document text must never carry patient identifiers; identifiers
   in payloads are forbidden in this tier.

---

## 3. Components

| Component | Impl | Notes |
|---|---|---|
| Vector Database | `document_chunks` + `VectorStore` (JSONB, cosine) | pgvector-ready |
| Embeddings | `EmbeddingEngine` (`mock` \| `ollama`) | offline adapters |
| Document Loader registry | `service/loaders/registry.py` | extension/kind -> loader |
| PDF Loader | `pdf_loader.py` (`pypdf`, lazy import) | page-aware extraction |
| Word Loader | `word_loader.py` (`python-docx`, lazy import) | headings + tables |
| Hospital SOP Loader | `sop_loader.py` (structured JSON) | sections/steps normalization |
| Clinical Guidelines | `GUIDELINE` corpus + text/md/pdf/word loaders | existing |
| Drug Formulary | `FORMULARY`/`MEDICATION` + `formulary_loader.py` | CSV/JSON monographs |
| Policies | `POLICY` corpus + text/md/pdf/word loaders | existing |
| Medical Books | `TEXTBOOK` + `book_loader.py` | per-chapter docs |
| Medical Journals | `JOURNAL` + `journal_loader.py` | per-article docs |
| AI search surface | `POST /api/v1/knowledge/search` | scoped by doc_type/corpus |

---

## 4. Document Type Catalog

| doc_type | Sources | Loader(s) |
|---|---|---|
| `GUIDELINE` | clinical practice guidelines | pdf/word/text/markdown |
| `POLICY` | hospital operational & safety policies | pdf/word/text/markdown |
| `PROTOCOL` | hospital SOPs | `sop` JSON |
| `FORMULARY` | drug formulary | `formulary` CSV/JSON |
| `MEDICATION` | medication monographs | `formulary` (rate: MEDICATION) |
| `TEXTBOOK` | medical books | `book` JSON / pdf / markdown |
| `JOURNAL` | medical journals | `journal` JSON / pdf |
| `LAB_REFERENCE` | lab reference ranges | pdf/csv/text |
| `REGULATORY` | regulatory filings | pdf/text |

---

## 5. Ingestion Pipeline

```
 upload (multipart: file, doc_type, kind?, title?, auto_approve?)
    │
    ▼                                service/loaders
 Loader resolution ───────────────► registry.get(filename, kind)
    │  .pdf→PdfLoader  .docx→WordLoader  .txt/.md→TextLoader
    │  .csv→Formulary(.csv)  .json→ kind: sop|formulary|book|journal
    ▼
 Extract ─► LoadedDocument(s): {title, doc_type, text, source_format,
    │                          ingestion_ref, metadata}
    ▼
 +---------------- KnowledgeService.ingest_loaded ----------------+
 | dedupe(title,version) → skip existing                       |
 | KnowledgeDocument(status=PENDING, hash=sha256(text),        |
 |                   source_format, ingestion_ref)             |
 | chunk(text, size, overlap) → embed(each chunk)              |
 | status → APPROVED (auto) or INDEXED (review)                |
 +-------------------------------------------------------------+
    ▼
 Vector search (cosine ≥ threshold) — AI agents:: search(scoped)
```

CPU-heavy loader work runs in a worker thread (`asyncio.to_thread`) so the
async event loop stays responsive; uploads are capped at
`max_upload_bytes` (default 20 MiB) and files render at most
`max_documents_per_file` documents.

---

## 6. Loader Contract

```
LoadedDocument(title, doc_type, text, source_format, ingestion_ref, metadata)

DocumentLoader
  .formats : tuple[str, ...]   # extensions, e.g. (".pdf",)
  .kind    : str               # "pdf" | "word" | "sop" | ...
  .load(raw, filename) -> list[LoadedDocument]
```

- `kind` is required for `.json` (ambiguous: sop vs formulary vs book vs journal).
- `.csv` defaults to `formulary` when `doc_type` is `FORMULARY`/`MEDICATION`.
- Binary loaders import their parser **lazily**; if the optional dependency is
  absent the loader raises `LOADER_UNAVAILABLE` (503) instead of crashing.

---

## 7. Chunking & Embedding

- Default chunk 800 chars / 120 overlap, word-boundary aware (existing).
- Embedding dims: `mock` 256, `ollama` = model dim (e.g. 384 `nomic-embed-text`).
- Chunks store `embedding`, `embedding_model`, `embedding_dim` for
  re-embedding on model change.
- Structured documents (SOP/formulary/book/journal) attach rich `metadata_`
  (department, authors, journal, volume/issue, chapter, keywords, doi) so hits
  are explainable.

---

## 8. Search Surface (everything searchable by AI)

- `POST /search` `{query, doc_type?, corpus_key?, top_k, user_id}` — cosine
  scoring, threshold gate, scoped by doc_type or corpus, audited, returns
  `sources` with scores + document metadata.
- Consumed by `ai-service` RAG bridge (`POST /api/v1/knowledge/search`) and by
  every specialized agent (`SPECIALIZED_AI_AGENTS_ARCHITECTURE.md` §4).

---

## 9. Ingestion API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/knowledge/ingest` | multipart `file` + `doc_type`, `kind`, `title`, `auto_approve` |
| POST | `/api/v1/knowledge/documents` | raw text upsert (existing) |
| PATCH | `/api/v1/knowledge/documents/{id}/status` | human approval flow |

Response (EHOS envelope):
```
202/201 { "success": true, "data": {
  "ingested": [DocumentOut...], "added": 5, "skipped": 1 } }
```

---

## 10. Security & Governance

- Uploaded bytes are never dumped to disk; parsing happens in memory.
- Loader errors are sanitized (no raw exception text beyond a stable `code`).
- Ingested text is plain medical/operational content — PHI is rejected on
  intake by policy and principals (no patient identifiers).
- Only `INDEXED`/`APPROVED` docs are searchable; everything is audited.

---

## 11. Verification

- `pytest`: loader unit tests (real PDF via reportlab fixture, real DOCX via
  python-docx, structured JSON/CSV fixtures) + ingestion integration tests.
- `ruff check .` clean (line-length 120, selected rule set).

# END OF MEDICAL KNOWLEDGE BASE DESIGN