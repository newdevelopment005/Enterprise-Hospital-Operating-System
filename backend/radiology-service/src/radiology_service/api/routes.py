import uuid
from uuid import UUID

from ehos_common.outbox import Outbox
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from radiology_service.dto.schemas import (
    ModalityCreate,
    ModalityRead,
    ModalityUpdate,
    PaginatedResponse,
    RadiologyOrderCreate,
    RadiologyOrderRead,
    RadiologyOrderUpdate,
    RadiologyReportCreate,
    RadiologyReportRead,
    RadiologyReportSign,
    RadiologyReportUpdate,
    StudyComplete,
    StudyCreate,
    StudyRead,
    StudyStart,
)
from radiology_service.service.radiology_service import RadiologyError, service

router = APIRouter(prefix="/api/v1/radiology", tags=["radiology"])


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


# ---- Modalities ----

@router.post("/modalities", response_model=ModalityRead, status_code=status.HTTP_201_CREATED)
async def create_modality(payload: ModalityCreate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.create_modality(db, payload, actor_id)
    except RadiologyError as e:
        raise HTTPException(status_code=409 if e.code == "DUPLICATE_MODALITY" else 400, detail=e.message)


@router.get("/modalities/{modality_id}", response_model=ModalityRead)
async def get_modality(modality_id: UUID, db: AsyncSession = Depends(get_session)):
    modality = await service.get_modality(db, modality_id)
    if not modality:
        raise HTTPException(404, "Modality not found")
    return modality


@router.get("/modalities", response_model=PaginatedResponse)
async def list_modalities(active_only: bool = True, limit: int = Query(50, le=200), offset: int = 0, db: AsyncSession = Depends(get_session)):
    items = await service.list_modalities(db, active_only, limit, offset)
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.patch("/modalities/{modality_id}", response_model=ModalityRead)
async def update_modality(modality_id: UUID, payload: ModalityUpdate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.update_modality(db, modality_id, payload, actor_id)
    except RadiologyError as e:
        raise HTTPException(status_code=404 if e.code == "MODALITY_NOT_FOUND" else 400, detail=e.message)


@router.delete("/modalities/{modality_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_modality(modality_id: UUID, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        await service.deactivate_modality(db, modality_id, actor_id)
    except RadiologyError as e:
        raise HTTPException(status_code=404 if e.code == "MODALITY_NOT_FOUND" else 400, detail=e.message)


# ---- Orders ----

@router.post("/orders", response_model=RadiologyOrderRead, status_code=status.HTTP_201_CREATED)
async def create_order(payload: RadiologyOrderCreate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.create_order(db, payload, actor_id)
    except RadiologyError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.get("/orders/{order_id}", response_model=RadiologyOrderRead)
async def get_order(order_id: UUID, db: AsyncSession = Depends(get_session)):
    order = await service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    return order


@router.get("/orders", response_model=PaginatedResponse)
async def list_orders(
    patient_id: UUID | None = None, ordering_doctor: UUID | None = None,
    status_filter: str | None = Query(None, alias="status"), modality_code: str | None = None,
    limit: int = Query(50, le=200), offset: int = 0, db: AsyncSession = Depends(get_session),
):
    items = await service.list_orders(db, patient_id, ordering_doctor, status_filter, modality_code, limit, offset)
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.patch("/orders/{order_id}", response_model=RadiologyOrderRead)
async def update_order(order_id: UUID, payload: RadiologyOrderUpdate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.update_order(db, order_id, payload, actor_id)
    except RadiologyError as e:
        raise HTTPException(status_code=404 if e.code == "ORDER_NOT_FOUND" else 400, detail=e.message)


@router.post("/orders/{order_id}/cancel", response_model=RadiologyOrderRead)
async def cancel_order(order_id: UUID, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.cancel_order(db, order_id, actor_id)
    except RadiologyError as e:
        raise HTTPException(status_code=404 if e.code == "ORDER_NOT_FOUND" else 400, detail=e.message)


# ---- Studies ----

@router.post("/studies", response_model=StudyRead, status_code=status.HTTP_201_CREATED)
async def create_study(payload: StudyCreate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.create_study(db, payload, actor_id)
    except RadiologyError as e:
        raise HTTPException(status_code=409 if e.code == "STUDY_EXISTS" else 400 if e.code == "ORDER_NOT_FOUND" else 400, detail=e.message)


@router.get("/studies/{study_id}", response_model=StudyRead)
async def get_study(study_id: UUID, db: AsyncSession = Depends(get_session)):
    study = await service.get_study(db, study_id)
    if not study:
        raise HTTPException(404, "Study not found")
    return study


@router.post("/studies/{study_id}/start", response_model=StudyRead)
async def start_study(study_id: UUID, payload: StudyStart, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.start_study(db, study_id, payload, actor_id)
    except RadiologyError as e:
        raise HTTPException(status_code=404 if e.code == "STUDY_NOT_FOUND" else 400, detail=e.message)


@router.post("/studies/{study_id}/complete", response_model=StudyRead)
async def complete_study(study_id: UUID, payload: StudyComplete, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.complete_study(db, study_id, payload, actor_id)
    except RadiologyError as e:
        raise HTTPException(status_code=404 if e.code == "STUDY_NOT_FOUND" else 400, detail=e.message)


@router.post("/studies/{study_id}/cancel", response_model=StudyRead)
async def cancel_study(study_id: UUID, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.cancel_study(db, study_id, actor_id)
    except RadiologyError as e:
        raise HTTPException(status_code=404 if e.code == "STUDY_NOT_FOUND" else 400, detail=e.message)


# ---- Reports ----

@router.post("/reports", response_model=RadiologyReportRead, status_code=status.HTTP_201_CREATED)
async def create_report(payload: RadiologyReportCreate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.create_report(db, payload, actor_id)
    except RadiologyError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.get("/reports/{report_id}", response_model=RadiologyReportRead)
async def get_report(report_id: UUID, db: AsyncSession = Depends(get_session)):
    report = await service.get_report(db, report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    return report


@router.get("/reports", response_model=PaginatedResponse)
async def list_reports(
    patient_id: UUID | None = None, order_id: UUID | None = None,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, le=200), offset: int = 0, db: AsyncSession = Depends(get_session),
):
    items = await service.list_reports(db, patient_id, order_id, status_filter, limit, offset)
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.patch("/reports/{report_id}", response_model=RadiologyReportRead)
async def update_report(report_id: UUID, payload: RadiologyReportUpdate, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.update_report(db, report_id, payload, actor_id)
    except RadiologyError as e:
        raise HTTPException(status_code=404 if e.code == "REPORT_NOT_FOUND" else 400, detail=e.message)


@router.post("/reports/{report_id}/sign", response_model=RadiologyReportRead)
async def sign_report(report_id: UUID, payload: RadiologyReportSign, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.sign_report(db, report_id, payload, actor_id)
    except RadiologyError as e:
        raise HTTPException(status_code=404 if e.code == "REPORT_NOT_FOUND" else 400, detail=e.message)


@router.post("/reports/{report_id}/cancel", response_model=RadiologyReportRead)
async def cancel_report(report_id: UUID, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.cancel_report(db, report_id, actor_id)
    except RadiologyError as e:
        raise HTTPException(status_code=404 if e.code == "REPORT_NOT_FOUND" else 400, detail=e.message)
