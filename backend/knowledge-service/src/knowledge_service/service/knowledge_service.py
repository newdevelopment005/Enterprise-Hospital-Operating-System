"""KnowledgeService: documents, chunking, embeddings, retrieval, audit."""

from __future__ import annotations

import asyncio
import hashlib
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_service.configuration import KnowledgeSettings
from knowledge_service.dto import schemas as dto
from knowledge_service.entity.models import (
    DocumentChunk,
    KnowledgeAccessLog,
    KnowledgeCorpus,
    KnowledgeDocument,
)
from knowledge_service.service.corpora import DEFAULT_CORPORA
from knowledge_service.service.embedding import EmbeddingEngine, EmbeddingError
from knowledge_service.service.loaders import LoaderError, load_documents
from knowledge_service.service.vector import cosine


class KnowledgeError(Exception):
    """Domain error surfaced as an EHOS error response."""

    def __init__(self, error_code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_code = status_code


class IngestResult:
    """Outcome of a file ingestion: created docs, added count, skipped count."""

    def __init__(self, ingested: list[KnowledgeDocument], added: int, skipped: int):
        self.ingested = ingested
        self.added = added
        self.skipped = skipped


def _chunks(text: str, size: int, overlap: int) -> list[str]:
    """Split text into overlapping character chunks on word boundaries."""
    if len(text) <= size:
        return [text] if text.strip() else []
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            space = text.rfind(" ", start + 1, end)
            if space > start:
                end = space
        pieces.append(text[start:end].strip())
        if end >= len(text):
            break
        start = end - overlap
    return [p for p in pieces if p]


class KnowledgeService:
    """Owns all knowledge-domain operations for the RAG tier."""

    def __init__(self, settings: KnowledgeSettings):
        self.settings = settings
        self.embeddings = EmbeddingEngine(settings)

    # --- documents -----------------------------------------------------------

    async def upsert_document(self, session: AsyncSession, payload: dto.DocumentIn) -> KnowledgeDocument:
        existing = await self.get_verified_claim(session, payload.title, payload.version)
        if existing:
            raise KnowledgeError("DOCUMENT_EXISTS", f"title '{payload.title}' version already exists", 409)
        document = KnowledgeDocument(
            doc_type=payload.doc_type,
            title=payload.title,
            version=payload.version or 1,
            status="PENDING",
            source_uri=payload.source_uri,
            approved_by=uuid.UUID(payload.approved_by) if payload.approved_by else None,
            hash=hashlib.sha256(payload.content.encode("utf-8")).hexdigest(),
        )
        session.add(document)
        await session.flush()
        await self._embed_document(session, document, payload.content)
        document.status = "INDEXED"
        return document

    async def get_verified_claim(
        self, session: AsyncSession, title: str, version: int | None
    ) -> KnowledgeDocument | None:
        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.title == title,
            KnowledgeDocument.version == (version or 1),
            KnowledgeDocument.deleted_at.is_(None),
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def list_documents(
        self, session: AsyncSession, doc_type: str | None, limit: int, offset: int
    ) -> tuple[list[KnowledgeDocument], int]:
        stmt = select(KnowledgeDocument).where(KnowledgeDocument.deleted_at.is_(None))
        count_stmt = select(func.count()).select_from(stmt.subquery())
        if doc_type:
            stmt = stmt.where(KnowledgeDocument.doc_type == doc_type)
            count_stmt = select(func.count()).select_from(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.deleted_at.is_(None), KnowledgeDocument.doc_type == doc_type
                ).subquery()
            )
        total = (await session.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(KnowledgeDocument.created_at.desc()).limit(limit).offset(offset)
        rows = (await session.execute(stmt)).scalars().all()
        return list(rows), total

    async def get_document(self, session: AsyncSession, document_id: uuid.UUID) -> KnowledgeDocument:
        row = (
            await session.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.id == document_id, KnowledgeDocument.deleted_at.is_(None)
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise KnowledgeError("NOT_FOUND", "knowledge document not found", 404)
        return row

    async def set_document_status(
        self, session: AsyncSession, document_id: uuid.UUID, status: str
    ) -> KnowledgeDocument:
        document = await self.get_document(session, document_id)
        document.status = status
        if status == "APPROVED":
            from datetime import UTC, datetime

            document.published_at = datetime.now(UTC)
        return document

    async def remove_document(self, session: AsyncSession, document_id: uuid.UUID, reason: str) -> None:
        document = await self.get_document(session, document_id)
        document.status = "RETIRED"
        document.deleted_at = func.now()
        document.deletion_reason = reason or "removed"

    # --- chunks --------------------------------------------------------------

    async def list_chunks(
        self, session: AsyncSession, document_id: uuid.UUID
    ) -> list[DocumentChunk]:
        rows = (
            await session.execute(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id, DocumentChunk.deleted_at.is_(None))
                .order_by(DocumentChunk.chunk_index)
            )
        ).scalars().all()
        return list(rows)

    # --- embeddings ----------------------------------------------------------

    async def embed_text(self, text: str) -> list[float]:
        try:
            return await self.embeddings.embed(text)
        except EmbeddingError as err:
            raise KnowledgeError("EMBEDDING_FAILED", str(err), 503) from err

    async def _embed_document(self, session: AsyncSession, document: KnowledgeDocument, content: str) -> None:
        pieces = _chunks(content, self.settings.chunk_size, self.settings.chunk_overlap)
        if not pieces:
            raise KnowledgeError("EMPTY_CONTENT", "document content produced no chunks")
        document.chunk_count = len(pieces)
        for index, piece in enumerate(pieces):
            vector = await self.embeddings.embed(piece)
            chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=index,
                content=piece,
                token_count=len(piece.split()),
                embedding=vector,
                embedding_model=self.embeddings.model,
                embedding_dim=self.embeddings.dimensions,
                metadata_={"doc_type": document.doc_type, "title": document.title},
            )
            session.add(chunk)

    # --- ingestion (medical knowledge base loaders) -------------------------

    async def ingest_bytes(
        self,
        session: AsyncSession,
        *,
        filename: str,
        raw: bytes,
        doc_type: str,
        title: str | None = None,
        kind: str | None = None,
        auto_approve: bool = True,
    ) -> IngestResult:
        """Load a file via its loader, then chunk/embed each document."""
        if len(raw) > self.settings.max_upload_bytes:
            raise KnowledgeError("PAYLOAD_TOO_LARGE", "file exceeds the ingestion size limit", 413)

        try:
            loaded = await asyncio.to_thread(
                load_documents, raw, filename=filename, kind=kind, doc_type=doc_type, settings=self.settings
            )
        except LoaderError as err:
            raise KnowledgeError(_loader_code(err.code), err.message, _loader_status(err.code)) from err

        presented = [doc for doc in loaded if doc.doc_type in dto.DOC_TYPES]
        if len(presented) != len(loaded):
            unsupported = ", ".join(doc.doc_type for doc in set(loaded) - set(presented))
            raise KnowledgeError("INVALID_DOC_TYPE", f"unsupported document type(s): {unsupported}", 422)
        if len(presented) > self.settings.max_documents_per_file:
            raise KnowledgeError("TOO_MANY_DOCUMENTS", "file expands to too many documents", 413)

        if title and len(presented) == 1:
            presented[0].title = title

        ingested: list[KnowledgeDocument] = []
        added = 0
        skipped = 0
        for document in presented:
            existing = await self.get_verified_claim(session, document.title, 1)
            if existing is not None:
                ingested.append(existing)
                skipped += 1
                continue
            row = KnowledgeDocument(
                doc_type=document.doc_type,
                title=document.title,
                version=1,
                status="PENDING",
                source_uri=document.ingestion_ref,
                source_format=document.source_format,
                ingestion_ref=document.ingestion_ref,
                hash=hashlib.sha256(document.text.encode("utf-8")).hexdigest(),
            )
            session.add(row)
            await session.flush()
            await self._embed_document(session, row, document.text)
            if document.metadata:
                rows = await self.list_chunks(session, row.id)
                for chunk in rows:
                    chunk.metadata_ = {**(chunk.metadata_ or {}), **document.metadata}
            row.status = "APPROVED" if auto_approve else "INDEXED"
            ingested.append(row)
            added += 1
        return IngestResult(ingested=ingested, added=added, skipped=skipped)

    # --- retrieval -----------------------------------------------------------

    async def search(
        self, session: AsyncSession, payload: dto.SearchIn
    ) -> dto.SearchOut:
        query_vector = await self.embed_text(payload.query)
        stmt = (
            select(DocumentChunk, KnowledgeDocument)
            .join(KnowledgeDocument, DocumentChunk.document_id == KnowledgeDocument.id)
            .where(
                DocumentChunk.deleted_at.is_(None),
                KnowledgeDocument.deleted_at.is_(None),
                KnowledgeDocument.status.in_(("INDEXED", "APPROVED")),
            )
        )
        if payload.doc_type:
            stmt = stmt.where(KnowledgeDocument.doc_type == payload.doc_type)
        elif payload.corpus_key:
            corpus = (
                await session.execute(
                    select(KnowledgeCorpus).where(KnowledgeCorpus.key == payload.corpus_key)
                )
            ).scalar_one_or_none()
            if corpus is None or corpus.deleted_at is not None:
                raise KnowledgeError("CORPUS_NOT_FOUND", "knowledge corpus not found", 404)
            stmt = stmt.where(KnowledgeDocument.doc_type == corpus.doc_type)
        rows = (await session.execute(stmt)).all()

        scored: list[tuple[float, DocumentChunk, KnowledgeDocument]] = []
        for chunk, document in rows:
            if not chunk.embedding:
                continue
            score = cosine(query_vector, chunk.embedding)
            if score >= self.settings.similarity_threshold:
                scored.append((score, chunk, document))

        scored.sort(key=lambda item: item[0], reverse=True)
        hits: list[dto.SearchHit] = []
        for score, chunk, document in scored[: payload.top_k]:
            hits.append(
                dto.SearchHit(
                    chunk_id=str(chunk.id),
                    document_id=str(document.id),
                    document_title=document.title,
                    doc_type=document.doc_type,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    score=round(float(score), 6),
                    metadata=chunk.metadata_,
                )
            )

        session.add(
            KnowledgeAccessLog(
                user_id=uuid.UUID(payload.user_id) if payload.user_id else None,
                query=payload.query,
                permitted=True,
            )
        )
        return dto.SearchOut(query=payload.query, hits=hits, count=len(hits), embedding_model=self.embeddings.model)

    # --- corpora -------------------------------------------------------------

    async def list_corpora(self, session: AsyncSession) -> list[KnowledgeCorpus]:
        rows = (
            await session.execute(
                select(KnowledgeCorpus).where(KnowledgeCorpus.deleted_at.is_(None))
            )
        ).scalars().all()
        return list(rows)

    async def seed_defaults(self, session: AsyncSession) -> int:
        """Load the four bootstrapped corpora (idempotent)."""
        added = 0
        for corpus in DEFAULT_CORPORA:
            existing = (
                await session.execute(
                    select(KnowledgeCorpus).where(KnowledgeCorpus.key == corpus["key"])
                )
            ).scalar_one_or_none()
            if existing is None:
                existing = KnowledgeCorpus(
                    key=corpus["key"],
                    corpus_name=corpus["name"],
                    description=corpus["description"],
                    doc_type=corpus["doc_type"],
                    is_seeded=True,
                )
                session.add(existing)
                await session.flush()
            for doc in corpus["documents"]:
                claim = await self.get_verified_claim(session, doc["title"], 1)
                if claim is not None:
                    continue
                column = KnowledgeDocument(
                    doc_type=doc["doc_type"],
                    title=doc["title"],
                    version=1,
                    status="PENDING",
                    hash=hashlib.sha256(doc["content"].encode("utf-8")).hexdigest(),
                )
                session.add(column)
                await session.flush()
                await self._embed_document(session, column, doc["content"])
                column.status = "APPROVED"
                added += 1
        return added


# --- serializers ---------------------------------------------------------------


def document_out(document: KnowledgeDocument) -> dto.DocumentOut:
    return dto.DocumentOut(
        id=str(document.id),
        doc_type=document.doc_type,
        title=document.title,
        version=document.version,
        status=document.status,
        source_uri=document.source_uri,
        source_format=document.source_format,
        ingestion_ref=document.ingestion_ref,
        chunk_count=document.chunk_count,
        published_at=document.published_at,
        created_at=document.created_at,
    )


def chunk_out(chunk: DocumentChunk) -> dto.ChunkOut:
    return dto.ChunkOut(
        id=str(chunk.id),
        document_id=str(chunk.document_id),
        chunk_index=chunk.chunk_index,
        content=chunk.content,
        token_count=chunk.token_count,
        metadata=chunk.metadata_,
    )


def corpus_out(corpus: KnowledgeCorpus) -> dto.CorpusOut:
    return dto.CorpusOut(
        id=str(corpus.id),
        key=corpus.key,
        name=corpus.corpus_name,
        description=corpus.description,
        doc_type=corpus.doc_type,
        is_seeded=corpus.is_seeded,
        created_at=corpus.created_at,
    )


def ingest_out(result: IngestResult) -> dict:
    """Serialize an ingestion outcome as an EHOS envelope payload."""
    return {
        "ingested": [document_out(doc) for doc in result.ingested],
        "added": result.added,
        "skipped": result.skipped,
    }


def _loader_code(code: str) -> str:
    return {
        "UNSUPPORTED_FORMAT": "UNSUPPORTED_FORMAT",
        "INVALID_DOC_TYPE": "INVALID_DOC_TYPE",
        "LOADER_UNAVAILABLE": "LOADER_UNAVAILABLE",
        "PARSE_ERROR": "PARSE_ERROR",
        "PAYLOAD_LIMIT": "PAYLOAD_TOO_LARGE",
    }.get(code, "INGESTION_FAILED")


def _loader_status(code: str) -> int:
    return {
        "UNSUPPORTED_FORMAT": 422,
        "INVALID_DOC_TYPE": 422,
        "LOADER_UNAVAILABLE": 503,
        "PARSE_ERROR": 422,
        "PAYLOAD_LIMIT": 413,
    }.get(code, 400)