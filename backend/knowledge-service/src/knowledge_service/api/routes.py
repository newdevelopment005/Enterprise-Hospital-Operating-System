"""REST API for the knowledge-service (RAG tier).

Responses use the standard EHOS envelope {"success": true, "data": ...}.
"""

from __future__ import annotations

import uuid

from ehos_common.outbox import Outbox
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_service.dto import schemas as dto
from knowledge_service.service import knowledge_service as svc
from knowledge_service.service.eventing import publish_ingested

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


async def get_session(request: Request) -> AsyncSession:
    async with request.app.state.database.session() as session:
        outbox = Outbox()
        session.info["outbox"] = outbox
        try:
            yield session
            await session.commit()
            # Only publish staged events once the write is durable.
            await outbox.flush(getattr(request.app.state, "producer", None))
        except Exception:
            await session.rollback()
            outbox.discard()
            raise


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as err:
        raise svc.KnowledgeError("INVALID_UUID", f"'{value}' is not a valid UUID", 400) from err


def _s(request: Request) -> svc.KnowledgeService:
    return request.app.state.knowledge_service


def _ok(data, status_code: int = 200) -> dict:
    return {"success": True, "data": data, "statusCode": status_code}


# --- documents ---------------------------------------------------------------


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def upsert_document(payload: dto.DocumentIn, request: Request, session: AsyncSession = Depends(get_session)):
    document = await _s(request).upsert_document(session, payload)
    return _ok(svc.document_out(document), status.HTTP_201_CREATED)


@router.get("/documents")
async def list_documents(
    request: Request,
    session: AsyncSession = Depends(get_session),
    doc_type: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows, total = await _s(request).list_documents(session, doc_type, limit or 20, offset)
    return _ok({"items": [svc.document_out(r) for r in rows], "total": total})


@router.get("/documents/{document_id}")
async def get_document(document_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    document = await _s(request).get_document(session, _uuid(document_id))
    return _ok(svc.document_out(document))


@router.patch("/documents/{document_id}/status")
async def set_document_status(
    document_id: str, payload: dto.DocumentStatusIn, request: Request, session: AsyncSession = Depends(get_session)
):
    document = await _s(request).set_document_status(session, _uuid(document_id), payload.status)
    return _ok(svc.document_out(document))


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_document(
    document_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    reason: str = Query(default="removed"),
):
    await _s(request).remove_document(session, _uuid(document_id), reason)
    return None


@router.get("/documents/{document_id}/chunks")
async def list_chunks(document_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    rows = await _s(request).list_chunks(session, _uuid(document_id))
    return _ok({"items": [svc.chunk_out(r) for r in rows], "total": len(rows)})


# --- ingestion (medical knowledge base loaders) ------------------------------


@router.post("/ingest", status_code=status.HTTP_201_CREATED)
async def ingest_upload(
    request: Request,
    session: AsyncSession = Depends(get_session),
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    kind: str | None = Form(default=None),
    title: str | None = Form(default=None),
    auto_approve: bool = Form(default=True),
):
    if doc_type not in dto.DOC_TYPES:
        raise svc.KnowledgeError("INVALID_DOC_TYPE", f"unknown doc_type '{doc_type}'", 422)
    if kind and kind not in dto.LOADER_KINDS:
        raise svc.KnowledgeError("UNSUPPORTED_FORMAT", f"unknown loader kind '{kind}'", 422)
    raw = await file.read()
    result = await _s(request).ingest_bytes(
        session,
        filename=file.filename or "upload",
        raw=raw,
        doc_type=doc_type,
        title=title,
        kind=kind,
        auto_approve=auto_approve,
    )
    await publish_ingested(getattr(request.app.state, "producer", None), result.ingested, session.info.get("outbox"))
    return _ok(svc.ingest_out(result), status.HTTP_201_CREATED)


# --- retrieval ---------------------------------------------------------------


@router.post("/search")
async def search(payload: dto.SearchIn, request: Request, session: AsyncSession = Depends(get_session)):
    result = await _s(request).search(session, payload)
    return _ok(result.model_dump())


@router.post("/embed")
async def embed_text(payload: dto.EmbedIn, request: Request):
    vector = await _s(request).embed_text(payload.text)
    return _ok({"embedding": vector, "dimensions": len(vector), "model": _s(request).embeddings.model})


# --- corpora -----------------------------------------------------------------


@router.get("/corpora")
async def list_corpora(request: Request, session: AsyncSession = Depends(get_session)):
    rows = await _s(request).list_corpora(session)
    return _ok({"items": [svc.corpus_out(r) for r in rows], "total": len(rows)})


@router.post("/seed-defaults", status_code=status.HTTP_201_CREATED)
async def seed_defaults(request: Request, session: AsyncSession = Depends(get_session)):
    added = await _s(request).seed_defaults(session)
    return _ok({"added": added}, status.HTTP_201_CREATED)