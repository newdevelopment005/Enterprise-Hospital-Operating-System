"""REST API for the pharmacy-service.

Endpoints under ``/api/v1/pharmacy`` return the standard EHOS envelope. The
service sits behind the API gateway which injects the OAuth2 token.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from ehos_common.api import success_response
from ehos_common.outbox import Outbox
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pharmacy_service.dto.schemas import DispenseIn, MedicationIn, ReturnIn, StockReceiveIn
from pharmacy_service.service.pharmacy_service import (
    PharmacyError,
    PharmacyService,
    _disp_out,
    _med_out,
)

router = APIRouter(prefix="/api/v1/pharmacy", tags=["pharmacy"])


async def get_session(request: Request) -> AsyncSession:
    async with request.app.state.database.session() as session:
        outbox = Outbox()
        session.info["outbox"] = outbox
        try:
            yield session
            await session.commit()
            # Publish staged events only after the write is durable; events
            # staged for a rolled-back transaction are discarded (no phantom
            # events when the DB commit fails).
            await outbox.flush(getattr(request.app.state, "producer", None))
        except Exception:
            await session.rollback()
            outbox.discard()
            raise


def get_service(request: Request) -> PharmacyService:
    return request.app.state.pharmacy_service


SvcDep = Annotated[PharmacyService, Depends(get_service)]


# ================================================================== catalog

@router.post("/medications", status_code=201)
async def create_medication(
    data: MedicationIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    med = await svc.create_medication(session, data)
    return success_response(_med_out(med))


@router.get("/medications")
async def search_medications(
    q: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    items, total = await svc.search_medications(session, q=q, limit=limit, offset=offset)
    return success_response({"medications": items, "total": total, "limit": limit})


# ================================================================== stock

@router.post("/stock/receive", status_code=201)
async def receive_stock(
    data: StockReceiveIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    row = await svc.receive_stock(session, data)
    return success_response({"id": str(row.id), "quantity": float(row.quantity)})


@router.get("/medications/{medication_id}/stock")
async def medication_stock(
    medication_id: str,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    return success_response(await svc.medication_stock(session, _uuid(medication_id)))


@router.get("/stock/expiring")
async def expiring_soon(
    days: int = Query(default=90, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    rows = await svc.expiring_soon(session, days)
    return success_response({"items": rows, "total": len(rows), "within_days": days})


# ================================================================== dispensing

@router.post("/dispense", status_code=201)
async def dispense(
    data: DispenseIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    record = await svc.dispense(session, data)
    return success_response(_disp_out(record))


@router.post("/dispensing/{record_id}/return")
async def return_dispensing(
    record_id: str,
    data: ReturnIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    record = await svc.return_dispensing(session, _uuid(record_id), data.reason)
    return success_response(_disp_out(record))


@router.get("/patients/{patient_id}/dispensing")
async def patient_history(
    patient_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    rows = await svc.patient_history(session, _uuid_str(patient_id), limit=limit)
    return success_response({"items": rows, "total": len(rows)})


# ================================================================== helpers

def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise PharmacyError("INVALID_ID", f"Invalid identifier: {value}", 422) from exc


def _uuid_str(value: str) -> str:
    _uuid(value)
    return value
