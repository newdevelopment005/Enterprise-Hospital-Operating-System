"""Regression tests: patient events are published only after the DB commit.

The ``get_session`` dependency stages events on the request outbox and flushes
them after commit, so a rolled-back transaction must never emit phantom events.
"""

import contextlib
import types

from ehos_common.db import Database

from patient_service.api.routes import get_session
from patient_service.dto.schemas import RegisterRequest
from patient_service.entity.models import Base
from patient_service.service.patient_service import PatientService

PATIENT_TOPIC = "clinical.patient.registered"


class FakeProducer:
    def __init__(self):
        self.published = []

    async def publish(self, topic, event, headers=None) -> None:
        self.published.append((topic, event.envelope()))


async def _request(db, service, producer):
    return types.SimpleNamespace(
        app=types.SimpleNamespace(
            state=types.SimpleNamespace(database=db, patient_service=service, producer=producer)
        )
    )


def _register() -> RegisterRequest:
    return RegisterRequest(
        first_name="Jane",
        last_name="Doe",
        date_of_birth="1990-05-15",
        gender="FEMALE",
        national_identifier="123-456789-1",
    )


async def test_event_published_only_after_commit(settings, tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'patient.db'}")
    await db.init_models(Base)
    producer = FakeProducer()
    service = PatientService(settings, producer=producer)

    request = await _request(db, service, producer)
    gen = get_session(request)
    session = await gen.__anext__()
    try:
        await service.register(session, _register())
        # nothing may hit the bus before the transaction commits
        assert producer.published == []
    finally:
        with contextlib.suppress(StopAsyncIteration):
            await gen.asend(None)  # commit -> flush outbox

    assert [t for t, _ in producer.published] == [PATIENT_TOPIC]
    await db.dispose()


async def test_rollback_discards_staged_events(settings, tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'patient.db'}")
    await db.init_models(Base)
    producer = FakeProducer()
    service = PatientService(settings, producer=producer)

    request = await _request(db, service, producer)
    gen = get_session(request)
    session = await gen.__anext__()
    try:
        await service.register(session, _register())
    finally:
        # the handler raises -> dependency rolls back and discards staged events
        with contextlib.suppress(RuntimeError):
            await gen.athrow(RuntimeError("boom"))

    assert producer.published == []
    await db.dispose()
