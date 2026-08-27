"""REST API for the prescription-service.

Endpoints under ``/api/v1/prescriptions`` return the standard EHOS envelope.
The service sits behind the API gateway which injects the OAuth2 token.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from ehos_common.api import success_response
from ehos_common.outbox import Outbox
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from prescription_service.dto.schemas import (
    AdministrationIn,
    AllergyIn,
    CancelIn,
    PrescriptionIn,
)
from prescription_service.service.prescription_service import (
    PrescriptionError,
    PrescriptionService,
    _allergy_out,
    _item_out,
    _mar_out,
    _rx_out,
)

router = APIRouter(prefix="/api/v1/prescriptions", tags=["prescriptions"])


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


def get_service(request: Request) -> PrescriptionService:
    return request.app.state.prescription_service


SvcDep = Annotated[PrescriptionService, Depends(get_service)]


# ================================================================== prescriptions

@router.post("", status_code=201)
async def create_prescription(
    data: PrescriptionIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    rx = await svc.create(session, data)
    return success_response(await svc.get_detail(session, rx.id))


@router.get("")
async def list_prescriptions(
    patient_id: str | None = Query(default=None),
    prescriber_id: str | None = Query(default=None),
    status: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    rows, total = await svc.list_prescriptions(
        session,
        patient_id=_opt(patient_id),
        prescriber_id=_opt(prescriber_id),
        status=status,
        limit=limit,
        offset=offset,
    )
    return success_response(
        {"prescriptions": [_rx_out(rx) for rx in rows], "total": total, "limit": limit}
    )


@router.get("/{rx_id}")
async def get_prescription(
    rx_id: str,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    return success_response(await svc.get_detail(session, _uuid(rx_id)))


@router.post("/{rx_id}/cancel")
async def cancel_prescription(
    rx_id: str,
    data: CancelIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    rx = await svc.cancel(session, _uuid(rx_id), data)
    return success_response(_rx_out(rx))


@router.post("/{rx_id}/pause")
async def pause_prescription(
    rx_id: str,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    rx = await svc.set_status(session, _uuid(rx_id), "PAUSED")
    return success_response(_rx_out(rx))


@router.post("/{rx_id}/resume")
async def resume_prescription(
    rx_id: str,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    rx = await svc.set_status(session, _uuid(rx_id), "ACTIVE")
    return success_response(_rx_out(rx))


@router.post("/{rx_id}/complete")
async def complete_prescription(
    rx_id: str,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    rx = await svc.set_status(session, _uuid(rx_id), "COMPLETED")
    return success_response(_rx_out(rx))


@router.post("/items/{item_id}/discontinue")
async def discontinue_item(
    item_id: str,
    reason: str | None = Query(default=None, max_length=500),
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    item = await svc.discontinue_item(session, _uuid(item_id), reason)
    return success_response(_item_out(item))


# ================================================================== MAR

@router.post("/administrations", status_code=201)
async def record_administration(
    data: AdministrationIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    mar = await svc.record_administration(session, data)
    return success_response(_mar_out(mar))


@router.get("/patients/{patient_id}/administrations")
async def list_administrations(
    patient_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    rows = await svc.list_administrations(session, _uuid_str(patient_id), limit=limit)
    return success_response({"items": [_mar_out(m) for m in rows], "total": len(rows)})


# ================================================================== allergies

@router.post("/patients/{patient_id}/allergies", status_code=201)
async def add_allergy(
    patient_id: str,
    data: AllergyIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    if data.patient_id != patient_id:
        raise PrescriptionError("MISMATCH", "patient_id in body must match the URL.", 422)
    allergy = await svc.add_allergy(session, data)
    return success_response(_allergy_out(allergy))


@router.get("/patients/{patient_id}/allergies")
async def list_allergies(
    patient_id: str,
    active_only: bool = True,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    rows = await svc.list_allergies(session, _uuid_str(patient_id), active_only=active_only)
    return success_response({"items": [_allergy_out(a) for a in rows], "total": len(rows)})


# ================================================================== helpers

def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise PrescriptionError("INVALID_ID", f"Invalid identifier: {value}", 422) from exc


def _opt(value: str | None) -> str | None:
    if value is None:
        return None
    _uuid(value)
    return value


def _uuid_str(value: str) -> str:
    _uuid(value)
    return value
