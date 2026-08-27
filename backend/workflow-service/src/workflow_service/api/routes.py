import uuid
from uuid import UUID

from ehos_common.outbox import Outbox
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from workflow_service.dto.schemas import (
    PaginatedResponse,
    WorkflowDefinitionCreate,
    WorkflowDefinitionRead,
    WorkflowDefinitionUpdate,
    WorkflowEventFire,
    WorkflowInstanceCreate,
    WorkflowInstanceRead,
    WorkflowTransitionRead,
)
from workflow_service.service.workflow_service import WorkflowError, service

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


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


# ---- Definitions ----

@router.post("/definitions", response_model=WorkflowDefinitionRead, status_code=status.HTTP_201_CREATED)
async def create_definition(payload: WorkflowDefinitionCreate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.create_definition(db, payload, actor_id)
    except WorkflowError as e:
        raise HTTPException(status_code=409 if e.code == "DUPLICATE_KEY" else 400, detail=e.message)


@router.get("/definitions/{definition_id}", response_model=WorkflowDefinitionRead)
async def get_definition(definition_id: UUID, db: AsyncSession = Depends(get_session)):
    defn = await service.get_definition(db, definition_id)
    if not defn:
        raise HTTPException(404, "Definition not found")
    return defn


@router.get("/definitions", response_model=PaginatedResponse)
async def list_definitions(active_only: bool = True, limit: int = Query(50, le=200), offset: int = 0, db: AsyncSession = Depends(get_session)):
    items = await service.list_definitions(db, active_only, limit, offset)
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.patch("/definitions/{definition_id}", response_model=WorkflowDefinitionRead)
async def update_definition(definition_id: UUID, payload: WorkflowDefinitionUpdate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.update_definition(db, definition_id, payload, actor_id)
    except WorkflowError as e:
        raise HTTPException(status_code=404 if e.code == "DEFINITION_NOT_FOUND" else 400, detail=e.message)


@router.delete("/definitions/{definition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_definition(definition_id: UUID, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        await service.deactivate_definition(db, definition_id, actor_id)
    except WorkflowError as e:
        raise HTTPException(status_code=404 if e.code == "DEFINITION_NOT_FOUND" else 400, detail=e.message)


# ---- Instances ----

@router.post("/instances", response_model=WorkflowInstanceRead, status_code=status.HTTP_201_CREATED)
async def create_instance(payload: WorkflowInstanceCreate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.create_instance(db, payload, actor_id)
    except WorkflowError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.get("/instances/{instance_id}", response_model=WorkflowInstanceRead)
async def get_instance(instance_id: UUID, db: AsyncSession = Depends(get_session)):
    instance = await service.get_instance(db, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    return instance


@router.get("/instances", response_model=PaginatedResponse)
async def list_instances(
    entity_type: str | None = None, entity_id: UUID | None = None,
    patient_id: UUID | None = None, status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, le=200), offset: int = 0, db: AsyncSession = Depends(get_session),
):
    items = await service.list_instances(db, entity_type, entity_id, patient_id, status_filter, limit, offset)
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.post("/instances/{instance_id}/fire", response_model=WorkflowInstanceRead)
async def fire_event(instance_id: UUID, payload: WorkflowEventFire, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.fire_event(db, instance_id, payload, actor_id)
    except WorkflowError as e:
        raise HTTPException(status_code=404 if e.code in ("INSTANCE_NOT_FOUND", "DEFINITION_NOT_FOUND") else 400, detail=e.message)


@router.post("/instances/{instance_id}/cancel", response_model=WorkflowInstanceRead)
async def cancel_instance(instance_id: UUID, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.cancel_instance(db, instance_id, actor_id)
    except WorkflowError as e:
        raise HTTPException(status_code=404 if e.code == "INSTANCE_NOT_FOUND" else 400, detail=e.message)


@router.post("/instances/{instance_id}/pause", response_model=WorkflowInstanceRead)
async def pause_instance(instance_id: UUID, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.pause_instance(db, instance_id, actor_id)
    except WorkflowError as e:
        raise HTTPException(status_code=404 if e.code == "INSTANCE_NOT_FOUND" else 400, detail=e.message)


@router.post("/instances/{instance_id}/resume", response_model=WorkflowInstanceRead)
async def resume_instance(instance_id: UUID, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.resume_instance(db, instance_id, actor_id)
    except WorkflowError as e:
        raise HTTPException(status_code=404 if e.code == "INSTANCE_NOT_FOUND" else 400, detail=e.message)


# ---- Transitions ----

@router.get("/instances/{instance_id}/transitions", response_model=list[WorkflowTransitionRead])
async def list_transitions(instance_id: UUID, db: AsyncSession = Depends(get_session)):
    return await service.list_transitions(db, instance_id)
