"""Pydantic DTOs for the knowledge-service REST API.

Field names snake_case matching the DDL. Validation mirrors the doc_type/status
CHECK constraints.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

DOC_TYPES = ("GUIDELINE", "POLICY", "PROTOCOL", "FORMULARY", "TEXTBOOK", "REGULATORY", "PATIENT_ED",
             "MEDICATION", "LAB_REFERENCE", "JOURNAL")
DOC_STATUSES = ("PENDING", "INDEXED", "APPROVED", "SUPERSEDED", "REJECTED", "RETIRED")
LOADER_KINDS = ("pdf", "word", "text", "markdown", "sop", "formulary", "book", "journal")


class DocumentIn(BaseModel):
    doc_type: str = Field(pattern=f"^({'|'.join(DOC_TYPES)})$")
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=500_000)
    source_uri: str | None = Field(default=None, max_length=4000)
    approved_by: str | None = Field(default=None, min_length=1)
    version: int | None = Field(default=None, ge=1)


class DocumentStatusIn(BaseModel):
    status: str = Field(pattern=f"^({'|'.join(DOC_STATUSES)})$")


class DocumentOut(BaseModel):
    id: str
    doc_type: str
    title: str
    version: int
    status: str
    source_uri: str | None
    source_format: str | None = None
    ingestion_ref: str | None = None
    chunk_count: int | None
    published_at: datetime | None
    created_at: datetime


class ChunkOut(BaseModel):
    id: str
    document_id: str
    chunk_index: int
    content: str
    token_count: int | None
    metadata: dict | None


class CorpusIn(BaseModel):
    key: str = Field(min_length=1, max_length=100, pattern="^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    doc_type: str | None = Field(default=None, pattern=f"^({'|'.join(DOC_TYPES)})$")


class CorpusOut(BaseModel):
    id: str
    key: str
    name: str
    description: str | None
    doc_type: str | None
    is_seeded: bool
    created_at: datetime


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    doc_type: str | None = Field(default=None, pattern=f"^({'|'.join(DOC_TYPES)})$")
    corpus_key: str | None = Field(default=None, max_length=100)
    top_k: int = Field(default=8, ge=1, le=50)
    user_id: str | None = Field(default=None, min_length=1)


class SearchHit(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    doc_type: str
    chunk_index: int
    content: str
    score: float
    metadata: dict | None


class SearchOut(BaseModel):
    query: str
    hits: list[SearchHit] = Field(default_factory=list)
    count: int = 0
    embedding_model: str


class EmbedIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class EmbedOut(BaseModel):
    embedding: list[float]
    dimensions: int
    model: str