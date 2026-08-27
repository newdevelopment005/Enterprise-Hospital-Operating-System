"""Tests for appointment booking, conflicts, rescheduling and lifecycle."""

import contextlib
import types
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from appointment_service.api.routes import get_session
from appointment_service.dto.schemas import AppointmentIn, CancelIn, RescheduleIn
from appointment_service.entity.models import Base
from appointment_service.service.appointment_service import (
    APPOINTMENT_CANCELLED_TOPIC,
    APPOINTMENT_CREATED_TOPIC,
    AppointmentError,
    AppointmentService,
)

PATIENT_ID = str(uuid.uuid4())
OTHER_PATIENT = str(uuid.uuid4())
PROVIDER_ID = str(uuid.uuid4())


class FakeProducer:
    def __init__(self):
        self.published = []

    async def publish(self, topic, event, headers=None) -> None:
        self.published.append((topic, event.envelope()))


def _booking(**overrides) -> AppointmentIn:
    payload = {
        "patient_id": PATIENT_ID,
        "provider_id": PROVIDER_ID,
        "appointment_type": "OUTPATIENT",
        "start_time": datetime.now(UTC) + timedelta(days=1),
        "reason": "Persistent cough",
    }
    payload.update(overrides)
    return AppointmentIn(**payload)


def _future(days: int, hour_offset: int = 0) -> datetime:
    start = (datetime.now(UTC) + timedelta(days=days)).replace(
        hour=9 + hour_offset, minute=0, second=0, microsecond=0
    )
    return start


# ---------------------------------------------------------------- validation

async def test_rejects_past_start_time(session, service):
    with pytest.raises(ValueError, match="past"):
        _booking(start_time=datetime.now(UTC) - timedelta(hours=2))


async def test_book_sets_end_time_and_duration(session, service):
    appt = await service.book(session, _booking(duration_min=45))
    assert appt.status == "SCHEDULED"
    assert appt.duration_min == 45
    assert appt.end_time - appt.start_time == timedelta(minutes=45)


# ---------------------------------------------------------------- conflicts

async def test_provider_double_booking_rejected(session, service):
    await service.book(session, _booking())
    with pytest.raises(AppointmentError) as err:
        await service.book(session, _booking())
    assert err.value.error_code == "SLOT_CONFLICT"
    assert err.value.status_code == 409


async def test_patient_double_booking_rejected_with_other_provider(session, service):
    other_provider = str(uuid.uuid4())
    await service.book(session, _booking(provider_id=None))
    with pytest.raises(AppointmentError) as err:
        await service.book(session, _booking(provider_id=other_provider))
    assert err.value.error_code == "PATIENT_DOUBLE_BOOKED"


async def test_same_provider_different_slot_ok(session, service):
    # fixed, far-apart slots so the test never collides with the wall clock
    await service.book(session, _booking(start_time=_future(2, 1)))
    second = await service.book(session, _booking(start_time=_future(2, 9)))
    assert second.status == "SCHEDULED"


async def test_cancelled_appointment_frees_the_slot(session, service):
    appt = await service.book(session, _booking())
    await service.cancel(session, appt.id, CancelIn(reason="Patient called off"))
    rebooked = await service.book(session, _booking())
    assert rebooked.id != appt.id


# ---------------------------------------------------------------- lifecycle

async def test_reschedule_moves_slot(session, service):
    appt = await service.book(session, _booking())
    new_start = _future(3)
    updated = await service.reschedule(session, appt.id, RescheduleIn(start_time=new_start))
    assert updated.start_time == new_start
    assert updated.version == 2


async def test_cannot_reschedule_cancelled(session, service):
    appt = await service.book(session, _booking())
    await service.cancel(session, appt.id, CancelIn(reason="x"))
    with pytest.raises(AppointmentError) as err:
        await service.reschedule(session, appt.id, RescheduleIn(start_time=_future(5)))
    assert err.value.error_code == "INVALID_STATUS"


async def test_complete_then_no_show_blocked(session, service):
    appt = await service.book(session, _booking())
    done = await service.complete(session, appt.id)
    assert done.status == "COMPLETED"
    with pytest.raises(AppointmentError):
        await service.mark_no_show(session, appt.id)


async def test_cancel_twice_rejected(session, service):
    appt = await service.book(session, _booking())
    await service.cancel(session, appt.id, CancelIn())
    with pytest.raises(AppointmentError):
        await service.cancel(session, appt.id, CancelIn())


# ------------------------------------------------------------ listing / availability

async def test_list_filters_by_patient(session, service):
    await service.book(session, _booking())
    await service.book(session, _booking(patient_id=OTHER_PATIENT, provider_id=str(uuid.uuid4())))
    rows, total = await service.list_appointments(session, patient_id=PATIENT_ID)
    assert total == 1
    assert rows[0].patient_id == uuid.UUID(PATIENT_ID)


async def test_upcoming_excludes_cancelled(session, service):
    appt = await service.book(session, _booking())
    await service.cancel(session, appt.id, CancelIn())
    rows, total = await service.list_appointments(session, patient_id=PATIENT_ID, upcoming_only=True)
    assert total == 0 and rows == []


async def test_availability_grid_marks_booked_slots(session, settings, service):
    day = (_future(7)).date()
    # book 09:00–09:30 UTC on that day
    start = datetime.combine(day, datetime.min.time(), tzinfo=UTC).replace(hour=9)
    await service.book(session, _booking(start_time=start))
    slots = await service.availability(session, day, provider_id=PROVIDER_ID)
    nine = next(s for s in slots if s["start"].startswith(f"{day.isoformat()}T09:00"))
    assert nine["available"] is False
    ten = next(s for s in slots if s["start"].startswith(f"{day.isoformat()}T10:00"))
    assert ten["available"] is True


# ---------------------------------------------------------------- outbox events

async def test_events_published_only_after_commit(settings, tmp_path):
    from ehos_common.db import Database

    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'scheduling.db'}")
    await db.init_models(Base)
    producer = FakeProducer()
    service = AppointmentService(settings, producer=producer)

    request = types.SimpleNamespace(
        app=types.SimpleNamespace(
            state=types.SimpleNamespace(database=db, appointment_service=service, producer=producer)
        )
    )
    gen = get_session(request)
    session = await gen.__anext__()
    try:
        await service.book(session, _booking())
        # nothing may hit the bus before the transaction commits
        assert producer.published == []
    finally:
        with contextlib.suppress(StopAsyncIteration):
            await gen.asend(None)  # commit -> flush outbox

    topics = [t for t, _ in producer.published]
    assert topics == [APPOINTMENT_CREATED_TOPIC]
    envelope = producer.published[0][1]
    assert envelope["payload"]["patientId"] == PATIENT_ID
    await db.dispose()


async def test_rollback_discards_staged_events(settings, tmp_path):
    from ehos_common.db import Database

    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'scheduling.db'}")
    await db.init_models(Base)
    producer = FakeProducer()
    service = AppointmentService(settings, producer=producer)

    request = types.SimpleNamespace(
        app=types.SimpleNamespace(
            state=types.SimpleNamespace(database=db, appointment_service=service, producer=producer)
        )
    )
    gen = get_session(request)
    session = await gen.__anext__()
    try:
        await service.book(session, _booking())
    finally:
        # the handler raises -> dependency rolls back and discards staged events
        with contextlib.suppress(RuntimeError):
            await gen.athrow(RuntimeError("boom"))

    assert producer.published == []
    await db.dispose()


async def test_cancel_publishes_event(settings, tmp_path):
    from ehos_common.db import Database

    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'scheduling.db'}")
    await db.init_models(Base)
    producer = FakeProducer()
    service = AppointmentService(settings, producer=producer)

    request = types.SimpleNamespace(
        app=types.SimpleNamespace(
            state=types.SimpleNamespace(database=db, appointment_service=service, producer=producer)
        )
    )

    async with db.session() as raw:
        appt = await service.book(raw, _booking())
        await raw.commit()

    gen = get_session(request)
    session = await gen.__anext__()
    try:
        await service.cancel(session, appt.id, CancelIn(reason="done"))
    finally:
        with contextlib.suppress(StopAsyncIteration):
            await gen.asend(None)

    # the booking ran without a request outbox -> immediate publish; the cancel
    # went through the outbox and must appear only after commit
    assert [t for t, _ in producer.published] == [
        APPOINTMENT_CREATED_TOPIC,
        APPOINTMENT_CANCELLED_TOPIC,
    ]
    await db.dispose()
