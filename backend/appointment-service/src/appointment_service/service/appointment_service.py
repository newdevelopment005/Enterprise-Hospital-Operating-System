"""Business logic for appointment booking, rescheduling, cancellation, completion.

Publishes ``AppointmentCreated`` / ``AppointmentRescheduled`` /
``AppointmentCancelled`` / ``AppointmentCompleted`` on the registry-catalog
topics (``clinical.appointment.*``) so the EHR, notification and analytics
services keep projections fresh (EVENT_BUS_SCHEMAS.md).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, time, timedelta

from ehos_common.events import DomainEvent
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from appointment_service.configuration import AppointmentSettings
from appointment_service.dto.schemas import (
    ACTIVE_STATUSES,
    AppointmentIn,
    CancelIn,
    RescheduleIn,
)
from appointment_service.entity.models import Appointment

log = logging.getLogger("appointment-service")

APPOINTMENT_CREATED_TOPIC = "clinical.appointment.created"
APPOINTMENT_RESCHEDULED_TOPIC = "clinical.appointment.rescheduled"
APPOINTMENT_CANCELLED_TOPIC = "clinical.appointment.cancelled"
APPOINTMENT_COMPLETED_TOPIC = "clinical.appointment.completed"

# eventType → canonical registry topic (mirrors the shared EventRegistry catalog)
_APPOINTMENT_TOPICS = {
    "AppointmentCreated": APPOINTMENT_CREATED_TOPIC,
    "AppointmentRescheduled": APPOINTMENT_RESCHEDULED_TOPIC,
    "AppointmentCancelled": APPOINTMENT_CANCELLED_TOPIC,
    "AppointmentCompleted": APPOINTMENT_COMPLETED_TOPIC,
}

# statuses that still occupy a slot
BOOKABLE_STATUSES = ("SCHEDULED", "REQUESTED")

# grace window so "upcoming" includes an appointment that just started
JUST_STARTED_GRACE = timedelta(minutes=1)


class AppointmentError(Exception):
    def __init__(self, error_code: str, message: str, status_code: int = 400):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AppointmentService:
    def __init__(self, settings: AppointmentSettings, producer=None):
        self.settings = settings
        self.producer = producer

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    def _end_for(self, start: datetime, duration_min: int | None) -> tuple[datetime, int]:
        duration = duration_min or self.settings.default_duration_min
        duration = max(self.settings.min_duration_min, min(self.settings.max_duration_min, duration))
        start = self._as_utc(start)
        return start + timedelta(minutes=duration), duration

    async def _publish(self, session: AsyncSession, event_type: str, appointment_id, details: dict) -> None:
        if self.producer is None:
            return
        try:
            topic = _APPOINTMENT_TOPICS.get(event_type, APPOINTMENT_CREATED_TOPIC)
            event = DomainEvent(
                event_type=event_type,
                source="appointment-service",
                user_id=None,
                payload={
                    "appointmentId": str(appointment_id),
                    "occurredAt": datetime.now(UTC).isoformat(),
                    **details,
                },
            )
            # Stage on the request outbox (published after commit) when the HTTP
            # dependency wired one; fall back to immediate publish (direct calls,
            # tests) so eventing still works without the request lifecycle.
            outbox = session.info.get("outbox")
            if outbox is not None:
                outbox.add(topic, event)
            else:
                await self.producer.publish(topic, event)
        except Exception:  # noqa: BLE001 - publishing must never break booking
            log.exception("failed to publish %s", event_type)

    async def _get_or_404(self, session: AsyncSession, appointment_id) -> Appointment:
        appointment = await session.get(Appointment, appointment_id)
        if appointment is None or appointment.deleted_at is not None:
            raise AppointmentError("APPOINTMENT_NOT_FOUND", "Appointment not found", 404)
        return appointment

    async def _ensure_no_overlap(
        self,
        session: AsyncSession,
        *,
        patient_id,
        provider_id,
        start: datetime,
        end: datetime,
        exclude_id=None,
    ) -> None:
        """Reject double-booking of the same provider or the same patient."""
        conditions = [
            Appointment.deleted_at.is_(None),
            Appointment.status.in_((*ACTIVE_STATUSES, *BOOKABLE_STATUSES)),
            Appointment.start_time < end,
            func.coalesce(Appointment.end_time, Appointment.start_time) > start,
        ]
        if exclude_id is not None:
            conditions.append(Appointment.id != exclude_id)

        if provider_id is not None:
            stmt = select(Appointment).where(
                and_(*conditions, Appointment.provider_id == provider_id)
            )
            if (await session.execute(stmt)).scalar_one_or_none() is not None:
                raise AppointmentError(
                    "SLOT_CONFLICT", "The provider already has an appointment in this time range.", 409
                )

        stmt = select(Appointment).where(and_(*conditions, Appointment.patient_id == patient_id))
        if (await session.execute(stmt)).scalar_one_or_none() is not None:
            raise AppointmentError(
                "PATIENT_DOUBLE_BOOKED", "The patient already has an appointment in this time range.", 409
            )

    # ------------------------------------------------------------ booking

    async def book(
        self, session: AsyncSession, data: AppointmentIn, actor: uuid.UUID | None = None
    ) -> Appointment:
        patient_id = uuid.UUID(data.patient_id)
        provider_id = uuid.UUID(data.provider_id) if data.provider_id else None
        department_id = uuid.UUID(data.department_id) if data.department_id else None
        end, duration = self._end_for(data.start_time, data.duration_min)

        await self._ensure_no_overlap(
            session, patient_id=patient_id, provider_id=provider_id,
            start=self._as_utc(data.start_time), end=end,
        )

        appointment = Appointment(
            patient_id=patient_id,
            provider_id=provider_id,
            department_id=department_id,
            appointment_type=data.appointment_type,
            start_time=self._as_utc(data.start_time),
            end_time=end,
            duration_min=duration,
            reason=data.reason,
            priority=data.priority,
            source=data.source,
            consultation_room=data.consultation_room,
            created_by=actor,
            status="SCHEDULED",
        )
        session.add(appointment)
        await session.flush()
        await self._publish(
            session,
            "AppointmentCreated",
            appointment.id,
            {
                "patientId": str(patient_id),
                "providerId": str(provider_id) if provider_id else None,
                "startAt": appointment.start_time.isoformat(),
                "appointmentType": data.appointment_type,
            },
        )
        return appointment

    # ------------------------------------------------------------ read / list

    async def get(self, session: AsyncSession, appointment_id) -> Appointment:
        return await self._get_or_404(session, appointment_id)

    async def list_appointments(
        self,
        session: AsyncSession,
        *,
        patient_id: str | None = None,
        provider_id: str | None = None,
        department_id: str | None = None,
        status: str | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        upcoming_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Appointment], int]:
        limit = min(max(1, limit), self.settings.search_max_limit)
        conditions = [Appointment.deleted_at.is_(None)]
        if patient_id:
            conditions.append(Appointment.patient_id == uuid.UUID(patient_id))
        if provider_id:
            conditions.append(Appointment.provider_id == uuid.UUID(provider_id))
        if department_id:
            conditions.append(Appointment.department_id == uuid.UUID(department_id))
        if status:
            conditions.append(Appointment.status == status.upper())
        if from_time:
            conditions.append(Appointment.start_time >= self._as_utc(from_time))
        if to_time:
            conditions.append(Appointment.start_time <= self._as_utc(to_time))
        if upcoming_only:
            conditions.append(
                and_(
                    Appointment.status.in_((*ACTIVE_STATUSES, *BOOKABLE_STATUSES)),
                    Appointment.start_time >= datetime.now(UTC) - JUST_STARTED_GRACE,
                )
            )

        where = and_(*conditions)
        total = (
            await session.execute(select(func.count()).select_from(Appointment).where(where))
        ).scalar_one()
        rows = (
            (
                await session.execute(
                    select(Appointment).where(where).order_by(Appointment.start_time).limit(limit).offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    # ------------------------------------------------------------ lifecycle

    async def reschedule(
        self, session: AsyncSession, appointment_id, data: RescheduleIn, actor=None
    ) -> Appointment:
        appointment = await self._get_or_404(session, appointment_id)
        if appointment.status not in (*ACTIVE_STATUSES, *BOOKABLE_STATUSES):
            raise AppointmentError(
                "INVALID_STATUS",
                f"Cannot reschedule an appointment with status {appointment.status}.",
                409,
            )

        old_start = appointment.start_time
        end, duration = self._end_for(data.start_time, data.duration_min)
        await self._ensure_no_overlap(
            session,
            patient_id=appointment.patient_id,
            provider_id=appointment.provider_id,
            start=self._as_utc(data.start_time),
            end=end,
            exclude_id=appointment.id,
        )

        appointment.start_time = self._as_utc(data.start_time)
        appointment.end_time = end
        appointment.duration_min = duration
        appointment.version += 1
        appointment.updated_by = actor
        await session.flush()
        await self._publish(
            session,
            "AppointmentRescheduled",
            appointment.id,
            {
                "patientId": str(appointment.patient_id),
                "oldStartAt": old_start.isoformat(),
                "newStartAt": appointment.start_time.isoformat(),
            },
        )
        return appointment

    async def cancel(
        self, session: AsyncSession, appointment_id, data: CancelIn, actor=None
    ) -> Appointment:
        appointment = await self._get_or_404(session, appointment_id)
        if appointment.status in ("CANCELLED", "COMPLETED", "NO_SHOW"):
            raise AppointmentError(
                "INVALID_STATUS",
                f"Cannot cancel an appointment with status {appointment.status}.",
                409,
            )
        appointment.status = "CANCELLED"
        appointment.cancellation_reason = data.reason
        appointment.cancelled_at = datetime.now(UTC)
        appointment.cancelled_by = actor
        appointment.updated_by = actor
        appointment.version += 1
        await session.flush()
        await self._publish(
            session,
            "AppointmentCancelled",
            appointment.id,
            {"patientId": str(appointment.patient_id), "reason": data.reason},
        )
        return appointment

    async def complete(self, session: AsyncSession, appointment_id, actor=None) -> Appointment:
        appointment = await self._get_or_404(session, appointment_id)
        if appointment.status in ("CANCELLED", "COMPLETED", "NO_SHOW"):
            raise AppointmentError(
                "INVALID_STATUS",
                f"Cannot complete an appointment with status {appointment.status}.",
                409,
            )
        appointment.status = "COMPLETED"
        appointment.end_time = datetime.now(UTC)
        appointment.updated_by = actor
        appointment.version += 1
        await session.flush()
        await self._publish(
            session,
            "AppointmentCompleted",
            appointment.id,
            {"patientId": str(appointment.patient_id)},
        )
        return appointment

    async def mark_no_show(self, session: AsyncSession, appointment_id, actor=None) -> Appointment:
        appointment = await self._get_or_404(session, appointment_id)
        if appointment.status in ("CANCELLED", "COMPLETED", "NO_SHOW"):
            raise AppointmentError(
                "INVALID_STATUS",
                f"Cannot mark an appointment with status {appointment.status} as no-show.",
                409,
            )
        appointment.status = "NO_SHOW"
        appointment.updated_by = actor
        appointment.version += 1
        await session.flush()
        await self._publish(
            session,
            "AppointmentNoShow",
            appointment.id,
            {"patientId": str(appointment.patient_id)},
        )
        return appointment

    # ------------------------------------------------------------ availability

    async def availability(
        self, session: AsyncSession, day, provider_id=None, department_id=None
    ) -> list[dict]:
        """Free slot grid for one clinic day (settings-driven hours)."""
        open_at = datetime.combine(day, time(hour=self.settings.clinic_open_hour), tzinfo=UTC)
        close_at = datetime.combine(day, time(hour=self.settings.clinic_close_hour), tzinfo=UTC)
        step = timedelta(minutes=self.settings.slot_minutes)

        conditions = [
            Appointment.deleted_at.is_(None),
            Appointment.status.in_((*ACTIVE_STATUSES, *BOOKABLE_STATUSES)),
            Appointment.start_time >= open_at,
            Appointment.start_time < close_at,
        ]
        if provider_id:
            conditions.append(Appointment.provider_id == uuid.UUID(provider_id))
        elif department_id:
            conditions.append(Appointment.department_id == uuid.UUID(department_id))

        booked = (
            (await session.execute(select(Appointment).where(and_(*conditions)))).scalars().all()
        )

        slots: list[dict] = []
        cursor = open_at
        while cursor + step <= close_at:
            slot_end = cursor + step
            # normalize: SQLite may hand back naive datetimes
            conflict = any(
                self._as_utc(b.start_time) < slot_end
                and self._as_utc(b.end_time or b.start_time) > cursor
                for b in booked
            )
            slots.append({"start": cursor.isoformat(), "end": slot_end.isoformat(), "available": not conflict})
            cursor += step
        return slots