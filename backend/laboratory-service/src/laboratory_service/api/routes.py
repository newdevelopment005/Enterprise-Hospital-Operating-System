import uuid
from uuid import UUID

from ehos_common.outbox import Outbox
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from laboratory_service.dto.schemas import (
    LabOrderCreate,
    LabOrderRead,
    LabOrderUpdate,
    LabResultCreate,
    LabResultRead,
    LabResultUpdate,
    LabResultVerify,
    LabTestCreate,
    LabTestRead,
    LabTestUpdate,
    PaginatedResponse,
    SampleCollect,
    SampleCreate,
    SampleRead,
    SampleReceive,
    SampleReject,
)
from laboratory_service.service.laboratory_service import LaboratoryError, service

router = APIRouter(prefix="/api/v1/laboratory", tags=["laboratory"])


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


# ---- LabTest ----

@router.post("/tests", response_model=LabTestRead, status_code=status.HTTP_201_CREATED)
async def create_test(
    payload: LabTestCreate,
    db: AsyncSession = Depends(get_session),
    actor_id: UUID = Depends(get_actor),
):
    try:
        return await service.create_test(db, payload, actor_id)
    except LaboratoryError as e:
        raise HTTPException(status_code=409 if e.code == "DUPLICATE_TEST" else 400, detail=e.message)


@router.get("/tests/{test_id}", response_model=LabTestRead)
async def get_test(test_id: UUID, db: AsyncSession = Depends(get_session)):
    test = await service.get_test(db, test_id)
    if not test:
        raise HTTPException(404, "Test not found")
    return test


@router.get("/tests", response_model=PaginatedResponse)
async def list_tests(
    category: str | None = None,
    active_only: bool = True,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_session),
):
    items = await service.list_tests(db, category, active_only, limit, offset)
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.patch("/tests/{test_id}", response_model=LabTestRead)
async def update_test(
    test_id: UUID,
    payload: LabTestUpdate,
    db: AsyncSession = Depends(get_session),
    actor_id: UUID = Depends(get_actor),
):
    try:
        return await service.update_test(db, test_id, payload, actor_id)
    except LaboratoryError as e:
        raise HTTPException(status_code=404 if e.code == "TEST_NOT_FOUND" else 400, detail=e.message)


@router.delete("/tests/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_test(test_id: UUID, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        await service.deactivate_test(db, test_id, actor_id)
    except LaboratoryError as e:
        raise HTTPException(status_code=404 if e.code == "TEST_NOT_FOUND" else 400, detail=e.message)


# ---- LabOrder ----

@router.post("/orders", response_model=LabOrderRead, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: LabOrderCreate,
    db: AsyncSession = Depends(get_session),
    actor_id: UUID = Depends(get_actor),
):
    try:
        return await service.create_order(db, payload, actor_id)
    except LaboratoryError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.get("/orders/{order_id}", response_model=LabOrderRead)
async def get_order(order_id: UUID, db: AsyncSession = Depends(get_session)):
    order = await service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    return order


@router.get("/orders", response_model=PaginatedResponse)
async def list_orders(
    patient_id: UUID | None = None,
    ordering_doctor: UUID | None = None,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_session),
):
    items = await service.list_orders(db, patient_id, ordering_doctor, status_filter, limit, offset)
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.patch("/orders/{order_id}", response_model=LabOrderRead)
async def update_order(
    order_id: UUID,
    payload: LabOrderUpdate,
    db: AsyncSession = Depends(get_session),
    actor_id: UUID = Depends(get_actor),
):
    try:
        return await service.update_order(db, order_id, payload, actor_id)
    except LaboratoryError as e:
        raise HTTPException(status_code=404 if e.code == "ORDER_NOT_FOUND" else 400, detail=e.message)


@router.post("/orders/{order_id}/cancel", response_model=LabOrderRead)
async def cancel_order(order_id: UUID, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.cancel_order(db, order_id, actor_id)
    except LaboratoryError as e:
        raise HTTPException(status_code=404 if e.code == "ORDER_NOT_FOUND" else 400, detail=e.message)


# ---- Samples ----

@router.post("/samples", response_model=SampleRead, status_code=status.HTTP_201_CREATED)
async def create_sample(
    payload: SampleCreate,
    db: AsyncSession = Depends(get_session),
    actor_id: UUID = Depends(get_actor),
):
    try:
        return await service.create_sample(db, payload, actor_id)
    except LaboratoryError as e:
        raise HTTPException(status_code=409 if e.code == "DUPLICATE_BARCODE" else 400, detail=e.message)


@router.post("/samples/{sample_id}/collect", response_model=SampleRead)
async def collect_sample(
    sample_id: UUID,
    payload: SampleCollect,
    db: AsyncSession = Depends(get_session),
    actor_id: UUID = Depends(get_actor),
):
    try:
        return await service.collect_sample(db, sample_id, payload, actor_id)
    except LaboratoryError as e:
        raise HTTPException(status_code=404 if e.code == "SAMPLE_NOT_FOUND" else 400, detail=e.message)


@router.post("/samples/{sample_id}/receive", response_model=SampleRead)
async def receive_sample(
    sample_id: UUID,
    payload: SampleReceive,
    db: AsyncSession = Depends(get_session),
    actor_id: UUID = Depends(get_actor),
):
    try:
        return await service.receive_sample(db, sample_id, payload, actor_id)
    except LaboratoryError as e:
        raise HTTPException(status_code=404 if e.code == "SAMPLE_NOT_FOUND" else 400, detail=e.message)


@router.post("/samples/{sample_id}/reject", response_model=SampleRead)
async def reject_sample(
    sample_id: UUID,
    payload: SampleReject,
    db: AsyncSession = Depends(get_session),
    actor_id: UUID = Depends(get_actor),
):
    try:
        return await service.reject_sample(db, sample_id, payload, actor_id)
    except LaboratoryError as e:
        raise HTTPException(status_code=404 if e.code == "SAMPLE_NOT_FOUND" else 400, detail=e.message)


# ---- LabResults ----

@router.post("/results", response_model=LabResultRead, status_code=status.HTTP_201_CREATED)
async def create_result(
    payload: LabResultCreate,
    db: AsyncSession = Depends(get_session),
    actor_id: UUID = Depends(get_actor),
):
    try:
        return await service.create_result(db, payload, actor_id)
    except LaboratoryError as e:
        raise HTTPException(status_code=404 if e.code in ("ORDER_ITEM_NOT_FOUND", "SAMPLE_NOT_FOUND") else 400, detail=e.message)


@router.get("/results/{result_id}", response_model=LabResultRead)
async def get_result(result_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await service.get_result(db, result_id)
    if not result:
        raise HTTPException(404, "Result not found")
    return result


@router.get("/results", response_model=PaginatedResponse)
async def list_results(
    patient_id: UUID | None = None,
    order_item_id: UUID | None = None,
    test_id: UUID | None = None,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_session),
):
    items = await service.list_results(db, patient_id, order_item_id, test_id, status_filter, limit, offset)
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.patch("/results/{result_id}", response_model=LabResultRead)
async def update_result(
    result_id: UUID,
    payload: LabResultUpdate,
    db: AsyncSession = Depends(get_session),
    actor_id: UUID = Depends(get_actor),
):
    try:
        return await service.update_result(db, result_id, payload, actor_id)
    except LaboratoryError as e:
        raise HTTPException(status_code=404 if e.code == "RESULT_NOT_FOUND" else 400, detail=e.message)


@router.post("/results/{result_id}/verify", response_model=LabResultRead)
async def verify_result(
    result_id: UUID,
    payload: LabResultVerify,
    db: AsyncSession = Depends(get_session),
    actor_id: UUID = Depends(get_actor),
):
    try:
        return await service.verify_result(db, result_id, payload, actor_id)
    except LaboratoryError as e:
        raise HTTPException(status_code=404 if e.code == "RESULT_NOT_FOUND" else 400, detail=e.message)


@router.post("/results/{result_id}/cancel", response_model=LabResultRead)
async def cancel_result(result_id: UUID, db: AsyncSession = Depends(get_session), actor_id: UUID = Depends(get_actor)):
    try:
        return await service.cancel_result(db, result_id, actor_id)
    except LaboratoryError as e:
        raise HTTPException(status_code=404 if e.code == "RESULT_NOT_FOUND" else 400, detail=e.message)
