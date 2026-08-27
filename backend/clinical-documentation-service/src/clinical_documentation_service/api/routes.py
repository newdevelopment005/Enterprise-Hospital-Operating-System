import uuid
from uuid import UUID

from ehos_common.outbox import Outbox
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from clinical_documentation_service.dto.schemas import (
    ClinicalNoteCreate,
    ClinicalNoteRead,
    ClinicalNoteSign,
    ClinicalNoteUpdate,
    NoteVersionRead,
    PaginatedResponse,
    TemplateCreate,
    TemplateRead,
    TemplateUpdate,
)
from clinical_documentation_service.service.documentation_service import DocumentationError, service

router = APIRouter(prefix="/api/v1/documentation", tags=["documentation"])


async def get_session(request: Request) -> AsyncSession:
    async with request.app.state.database.session() as session:
        outbox = Outbox()
        session.info["outbox"] = outbox
        try:
            yield session
            await session.commit()
            # Publish staged events only after the write is durable; events
            # staged for a rolled-back transaction are discarded so no phantom
            # events are emitted when the DB commit fails.
            await outbox.flush(getattr(request.app.state, "producer", None))
        except Exception:
            await session.rollback()
            outbox.discard()
            raise


def get_actor(request: Request) -> UUID | None:
    raw = request.headers.get("X-User-Id")
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


# ---- Notes ----

@router.post("/notes", response_model=ClinicalNoteRead, status_code=status.HTTP_201_CREATED)
async def create_note(payload: ClinicalNoteCreate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.create_note(db, payload, actor_id)
    except DocumentationError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.get("/notes/{note_id}", response_model=ClinicalNoteRead)
async def get_note(note_id: UUID, db: AsyncSession = Depends(get_session)):
    note = await service.get_note(db, note_id)
    if not note:
        raise HTTPException(404, "Note not found")
    return note


@router.get("/notes", response_model=PaginatedResponse)
async def list_notes(
    patient_id: UUID | None = None, encounter_id: UUID | None = None,
    author_id: UUID | None = None, note_type: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, le=200), offset: int = 0, db: AsyncSession = Depends(get_session),
):
    items = await service.list_notes(db, patient_id, encounter_id, author_id, note_type, status_filter, limit, offset)
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.patch("/notes/{note_id}", response_model=ClinicalNoteRead)
async def update_note(note_id: UUID, payload: ClinicalNoteUpdate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.update_note(db, note_id, payload, actor_id)
    except DocumentationError as e:
        raise HTTPException(status_code=404 if e.code == "NOTE_NOT_FOUND" else 400, detail=e.message)


@router.post("/notes/{note_id}/sign", response_model=ClinicalNoteRead)
async def sign_note(note_id: UUID, payload: ClinicalNoteSign, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.sign_note(db, note_id, payload, actor_id)
    except DocumentationError as e:
        raise HTTPException(status_code=404 if e.code == "NOTE_NOT_FOUND" else 400, detail=e.message)


@router.post("/notes/{note_id}/cancel", response_model=ClinicalNoteRead)
async def cancel_note(note_id: UUID, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.cancel_note(db, note_id, actor_id)
    except DocumentationError as e:
        raise HTTPException(status_code=404 if e.code == "NOTE_NOT_FOUND" else 400, detail=e.message)


@router.get("/notes/{note_id}/versions", response_model=list[NoteVersionRead])
async def list_versions(note_id: UUID, db: AsyncSession = Depends(get_session)):
    return await service.list_versions(db, note_id)


# ---- Templates ----

@router.post("/templates", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(payload: TemplateCreate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    return await service.create_template(db, payload, actor_id)


@router.get("/templates/{template_id}", response_model=TemplateRead)
async def get_template(template_id: UUID, db: AsyncSession = Depends(get_session)):
    tmpl = await service.get_template(db, template_id)
    if not tmpl:
        raise HTTPException(404, "Template not found")
    return tmpl


@router.get("/templates", response_model=PaginatedResponse)
async def list_templates(note_type: str | None = None, active_only: bool = True, limit: int = Query(50, le=200), offset: int = 0, db: AsyncSession = Depends(get_session)):
    items = await service.list_templates(db, note_type, active_only, limit, offset)
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.patch("/templates/{template_id}", response_model=TemplateRead)
async def update_template(template_id: UUID, payload: TemplateUpdate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.update_template(db, template_id, payload, actor_id)
    except DocumentationError as e:
        raise HTTPException(status_code=404 if e.code == "TEMPLATE_NOT_FOUND" else 400, detail=e.message)
