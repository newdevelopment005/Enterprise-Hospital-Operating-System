import uuid
from uuid import UUID

from ehos_common.outbox import Outbox
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from reporting_service.dto.schemas import (
    PaginatedResponse,
    ReportDefinitionCreate,
    ReportDefinitionRead,
    ReportDefinitionUpdate,
    ReportInstanceCreate,
    ReportInstanceRead,
    ScheduledReportCreate,
    ScheduledReportRead,
    ScheduledReportUpdate,
)
from reporting_service.service.reporting_service import ReportingError, service

router = APIRouter(prefix="/api/v1/reporting", tags=["reporting"])


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


# ── Definitions ─────────────────────────────────────────────────────────────────

@router.post("/definitions", response_model=ReportDefinitionRead, status_code=status.HTTP_201_CREATED)
async def create_definition(payload: ReportDefinitionCreate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    return await service.create_definition(db, payload, actor_id)


@router.get("/definitions/{definition_id}", response_model=ReportDefinitionRead)
async def get_definition(definition_id: UUID, db: AsyncSession = Depends(get_session)):
    defn = await service.get_definition(db, definition_id)
    if not defn:
        raise HTTPException(404, "Report definition not found")
    return defn


@router.get("/definitions", response_model=PaginatedResponse)
async def list_definitions(
    report_type: str | None = None, active_only: bool = True,
    limit: int = Query(50, le=200), offset: int = 0,
    db: AsyncSession = Depends(get_session),
):
    items = await service.list_definitions(db, report_type, active_only, limit, offset)
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.patch("/definitions/{definition_id}", response_model=ReportDefinitionRead)
async def update_definition(definition_id: UUID, payload: ReportDefinitionUpdate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.update_definition(db, definition_id, payload, actor_id)
    except ReportingError as e:
        raise HTTPException(status_code=404 if e.code == "DEFINITION_NOT_FOUND" else 400, detail=e.message)


# ── Instances ───────────────────────────────────────────────────────────────────

@router.post("/instances", response_model=ReportInstanceRead, status_code=status.HTTP_201_CREATED)
async def create_instance(payload: ReportInstanceCreate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.create_instance(db, payload, actor_id)
    except ReportingError as e:
        raise HTTPException(status_code=404 if e.code == "DEFINITION_NOT_FOUND" else 400, detail=e.message)


@router.get("/instances/{instance_id}", response_model=ReportInstanceRead)
async def get_instance(instance_id: UUID, db: AsyncSession = Depends(get_session)):
    instance = await service.get_instance(db, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    return instance


@router.get("/instances", response_model=PaginatedResponse)
async def list_instances(
    definition_id: UUID | None = None, requested_by: UUID | None = None,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, le=200), offset: int = 0,
    db: AsyncSession = Depends(get_session),
):
    items = await service.list_instances(db, definition_id, requested_by, status_filter, limit, offset)
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.post("/instances/{instance_id}/start", response_model=ReportInstanceRead)
async def start_instance(instance_id: UUID, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.start_instance(db, instance_id, actor_id)
    except ReportingError as e:
        raise HTTPException(status_code=404 if e.code == "INSTANCE_NOT_FOUND" else 400, detail=e.message)


@router.post("/instances/{instance_id}/complete", response_model=ReportInstanceRead)
async def complete_instance(instance_id: UUID, result_data: dict = {}, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.complete_instance(db, instance_id, result_data, actor_id)
    except ReportingError as e:
        raise HTTPException(status_code=404 if e.code == "INSTANCE_NOT_FOUND" else 400, detail=e.message)


@router.post("/instances/{instance_id}/fail", response_model=ReportInstanceRead)
async def fail_instance(instance_id: UUID, error_message: str = "", db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.fail_instance(db, instance_id, error_message, actor_id)
    except ReportingError as e:
        raise HTTPException(status_code=404 if e.code == "INSTANCE_NOT_FOUND" else 400, detail=e.message)


@router.post("/instances/{instance_id}/cancel", response_model=ReportInstanceRead)
async def cancel_instance(instance_id: UUID, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.cancel_instance(db, instance_id, actor_id)
    except ReportingError as e:
        raise HTTPException(status_code=404 if e.code == "INSTANCE_NOT_FOUND" else 400, detail=e.message)


# ── Scheduled Reports ───────────────────────────────────────────────────────────

@router.post("/scheduled", response_model=ScheduledReportRead, status_code=status.HTTP_201_CREATED)
async def create_scheduled(payload: ScheduledReportCreate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.create_scheduled(db, payload, actor_id)
    except ReportingError as e:
        raise HTTPException(status_code=404 if e.code == "DEFINITION_NOT_FOUND" else 400, detail=e.message)


@router.get("/scheduled/{scheduled_id}", response_model=ScheduledReportRead)
async def get_scheduled(scheduled_id: UUID, db: AsyncSession = Depends(get_session)):
    sched = await service.get_scheduled(db, scheduled_id)
    if not sched:
        raise HTTPException(404, "Scheduled report not found")
    return sched


@router.get("/scheduled", response_model=PaginatedResponse)
async def list_scheduled(
    definition_id: UUID | None = None, active_only: bool = True,
    limit: int = Query(50, le=200), offset: int = 0,
    db: AsyncSession = Depends(get_session),
):
    items = await service.list_scheduled(db, definition_id, active_only, limit, offset)
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.patch("/scheduled/{scheduled_id}", response_model=ScheduledReportRead)
async def update_scheduled(scheduled_id: UUID, payload: ScheduledReportUpdate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.update_scheduled(db, scheduled_id, payload, actor_id)
    except ReportingError as e:
        raise HTTPException(status_code=404 if e.code == "SCHEDULED_NOT_FOUND" else 400, detail=e.message)


@router.post("/scheduled/{scheduled_id}/deactivate", response_model=ScheduledReportRead)
async def deactivate_scheduled(scheduled_id: UUID, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.deactivate_scheduled(db, scheduled_id, actor_id)
    except ReportingError as e:
        raise HTTPException(status_code=404 if e.code == "SCHEDULED_NOT_FOUND" else 400, detail=e.message)
