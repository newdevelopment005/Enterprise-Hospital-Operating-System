"""REST API for the appointment-service.

Endpoints under ``/api/v1/appointments`` return the standard EHOS envelope.
The service sits behind the API gateway which injects the OAuth2 token and
forwards the acting user id.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated

from ehos_common.api import success_response
from ehos_common.outbox import Outbox
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from appointment_service.dto.schemas import (
    AppointmentIn,
    CancelIn,
    RescheduleIn,
)
from appointment_service.service.appointment_service import (
    AppointmentError,
    AppointmentService,
)

router = APIRouter(prefix="/api/v1/appointments", tags=["appointments"])


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


def get_service(request: Request) -> AppointmentService:
    return request.app.state.appointment_service


SvcDep = Annotated[AppointmentService, Depends(get_service)]


# ================================================================== booking

@router.post("", status_code=201)
async def book_appointment(
    data: AppointmentIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    appointment = await svc.book(session, data)
    return success_response(_appointment_out(appointment))


@router.get("")
async def list_appointments(
    patient_id: str | None = Query(default=None),
    provider_id: str | None = Query(default=None),
    department_id: str | None = Query(default=None),
    status: str | None = Query(default=None, max_length=20),
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    upcoming_only: bool = Query(default=False, alias="upcoming"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    rows, total = await svc.list_appointments(
        session,
        patient_id=_optional_uuid(patient_id),
        provider_id=_optional_uuid(provider_id),
        department_id=_optional_uuid(department_id),
        status=status,
        from_time=from_time,
        to_time=to_time,
        upcoming_only=upcoming_only,
        limit=limit,
        offset=offset,
    )
    return success_response(
        {"appointments": [_appointment_out(a) for a in rows], "total": total, "limit": limit, "offset": offset}
    )


@router.get("/availability")
async def availability(
    day: date,
    provider_id: str | None = Query(default=None),
    department_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    slots = await svc.availability(
        session, day, provider_id=_optional_uuid(provider_id), department_id=_optional_uuid(department_id)
    )
    free = sum(1 for s in slots if s["available"])
    return success_response({"day": day.isoformat(), "slots": slots, "free": free, "total": len(slots)})


@router.get("/{appointment_id}")
async def get_appointment(
    appointment_id: str,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    appointment = await svc.get(session, _uuid(appointment_id))
    return success_response(_appointment_out(appointment))


# ================================================================== lifecycle

@router.post("/{appointment_id}/reschedule")
async def reschedule_appointment(
    appointment_id: str,
    data: RescheduleIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    appointment = await svc.reschedule(session, _uuid(appointment_id), data)
    return success_response(_appointment_out(appointment))


@router.post("/{appointment_id}/cancel")
async def cancel_appointment(
    appointment_id: str,
    data: CancelIn | None = None,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    appointment = await svc.cancel(session, _uuid(appointment_id), data or CancelIn())
    return success_response(_appointment_out(appointment))


@router.post("/{appointment_id}/complete")
async def complete_appointment(
    appointment_id: str,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    appointment = await svc.complete(session, _uuid(appointment_id))
    return success_response(_appointment_out(appointment))


@router.post("/{appointment_id}/no-show")
async def no_show_appointment(
    appointment_id: str,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    appointment = await svc.mark_no_show(session, _uuid(appointment_id))
    return success_response(_appointment_out(appointment))


# ================================================================== helpers

def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise AppointmentError("INVALID_ID", f"Invalid identifier: {value}", 422) from exc


def _optional_uuid(value: str | None) -> str | None:
    if value is None:
        return None
    _uuid(value)
    return value


def _appointment_out(a) -> dict:
    return {
        "id": str(a.id),
        "patient_id": str(a.patient_id),
        "provider_id": str(a.provider_id) if a.provider_id else None,
        "department_id": str(a.department_id) if a.department_id else None,
        "appointment_type": a.appointment_type,
        "start_time": a.start_time.isoformat(),
        "end_time": a.end_time.isoformat() if a.end_time else None,
        "duration_min": a.duration_min,
        "status": a.status,
        "reason": a.reason,
        "priority": a.priority,
        "source": a.source,
        "consultation_room": a.consultation_room,
        "cancellation_reason": a.cancellation_reason,
        "cancelled_at": a.cancelled_at.isoformat() if a.cancelled_at else None,
        "created_at": a.created_at.isoformat(),
    }
