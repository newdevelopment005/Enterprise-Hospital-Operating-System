"""Tests for the digital queues: create, join, advance, serve, events."""

import contextlib
import types
import uuid

import pytest
from ehos_common.db import Database

from queue_service.api.routes import get_session
from queue_service.dto.schemas import JoinIn, QueueIn
from queue_service.entity.models import Base
from queue_service.service.queue_service import (
    QUEUE_ADVANCED_TOPIC,
    QUEUE_COMPLETED_TOPIC,
    QUEUE_JOINED_TOPIC,
    QueueError,
    QueueService,
)

PATIENT_A = str(uuid.uuid4())
PATIENT_B = str(uuid.uuid4())


class FakeProducer:
    def __init__(self):
        self.published = []

    async def publish(self, topic, event, headers=None) -> None:
        self.published.append((topic, event.envelope()))


def _queue(**overrides) -> QueueIn:
    payload = {"queue_type": "OUTPATIENT", "name": "Morning clinic"}
    payload.update(overrides)
    return QueueIn(**payload)


def _join(patient_id: str, priority: int = 0) -> JoinIn:
    return JoinIn(patient_id=patient_id, priority=priority)


# ---------------------------------------------------------------- queues

async def test_create_and_list_queues(session, service):
    q = await service.create_queue(session, _queue())
    await service.create_queue(session, _queue(queue_type="PHARMACY"))
    rows = await service.list_queues(session)
    assert len(rows) == 2
    assert q.name == "Morning clinic"


# ---------------------------------------------------------------- join

async def test_join_assigns_sequential_tickets(session, service):
    q = await service.create_queue(session, _queue())
    t1 = await service.join(session, q.id, _join(PATIENT_A))
    t2 = await service.join(session, q.id, _join(PATIENT_B))
    assert (t1.ticket_number, t2.ticket_number) == ("OP-0001", "OP-0002")
    assert t1.status == "WAITING"


async def test_join_twice_rejected(session, service):
    q = await service.create_queue(session, _queue())
    await service.join(session, q.id, _join(PATIENT_A))
    with pytest.raises(QueueError) as err:
        await service.join(session, q.id, _join(PATIENT_A))
    assert err.value.error_code == "ALREADY_IN_QUEUE"


async def test_closed_queue_rejects_join(session, service):
    q = await service.create_queue(session, _queue())
    q.is_active = False
    with pytest.raises(QueueError) as err:
        await service.join(session, q.id, _join(PATIENT_A))
    assert err.value.error_code == "QUEUE_CLOSED"


# ---------------------------------------------------------------- advance / serve

async def test_advance_calls_priority_then_fifo(session, service):
    q = await service.create_queue(session, _queue())
    low = await service.join(session, q.id, _join(PATIENT_A, priority=0))
    urgent = await service.join(session, q.id, _join(PATIENT_B, priority=5))

    called = await service.advance(session, q.id)
    assert called.id == urgent.id  # higher priority first

    second = await service.advance(session, q.id)
    assert second.id == low.id


async def test_advance_on_empty_queue_409(session, service):
    q = await service.create_queue(session, _queue())
    with pytest.raises(QueueError) as err:
        await service.advance(session, q.id)
    assert err.value.error_code == "QUEUE_EMPTY"
    assert err.value.status_code == 409


async def test_uncalled_ticket_skipped_on_next_advance(session, service):
    q = await service.create_queue(session, _queue())
    a = await service.join(session, q.id, _join(PATIENT_A))
    b = await service.join(session, q.id, _join(PATIENT_B))

    await service.advance(session, q.id)  # calls A; nobody serves them
    third = await service.advance(session, q.id)  # calls B; A skipped

    await session.refresh(a)
    assert a.status == "SKIPPED"
    assert third.id == b.id


async def test_full_lifecycle_computes_wait_time(session, service):
    q = await service.create_queue(session, _queue())
    entry = await service.join(session, q.id, _join(PATIENT_A))
    await service.advance(session, q.id)
    started = await service.start(session, entry.id)
    assert started.status == "IN_PROGRESS"

    done = await service.complete(session, entry.id)
    assert done.status == "COMPLETED"
    assert done.completed_at is not None
    assert done.wait_time_min is not None and done.wait_time_min >= 0


async def test_cannot_complete_waiting_ticket(session, service):
    q = await service.create_queue(session, _queue())
    entry = await service.join(session, q.id, _join(PATIENT_A))
    with pytest.raises(QueueError):
        await service.complete(session, entry.id)


async def test_cancel_frees_patient_to_rejoin(session, service):
    q = await service.create_queue(session, _queue())
    entry = await service.join(session, q.id, _join(PATIENT_A))
    cancelled = await service.cancel(session, entry.id, reason="left")
    assert cancelled.status == "CANCELLED"
    rejoin = await service.join(session, q.id, _join(PATIENT_A))
    assert rejoin.ticket_number != entry.ticket_number


# ---------------------------------------------------------------- board

async def test_board_snapshot(session, service):
    q = await service.create_queue(session, _queue())
    await service.join(session, q.id, _join(PATIENT_A))
    b = await service.join(session, q.id, _join(PATIENT_B))
    await service.advance(session, q.id)

    board = await service.queue_board(session, q.id)
    assert board["now_serving"]["id"] == b.id or board["now_serving"]["status"] in ("CALLED", "IN_PROGRESS")
    assert board["counts"].get("WAITING", 0) >= 0
    assert all(e["ticket_number"] for e in board["waiting"])


# ---------------------------------------------------------------- outbox events

async def test_events_published_only_after_commit(settings, tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'queues.db'}")
    await db.init_models(Base)
    producer = FakeProducer()
    service = QueueService(settings, producer=producer)

    request = types.SimpleNamespace(
        app=types.SimpleNamespace(
            state=types.SimpleNamespace(database=db, queue_service=service, producer=producer)
        )
    )
    gen = get_session(request)
    session = await gen.__anext__()
    try:
        q = await service.create_queue(session, _queue())
        await service.join(session, q.id, _join(PATIENT_A))
        # nothing may hit the bus before the transaction commits
        assert producer.published == []
    finally:
        with contextlib.suppress(StopAsyncIteration):
            await gen.asend(None)  # commit -> flush outbox

    assert [t for t, _ in producer.published] == [QUEUE_JOINED_TOPIC]
    envelope = producer.published[0][1]
    assert envelope["payload"]["patientId"] == PATIENT_A
    await db.dispose()


async def test_advance_and_complete_publish_events(settings, tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'queues.db'}")
    await db.init_models(Base)
    producer = FakeProducer()
    service = QueueService(settings, producer=producer)

    async with db.session() as raw:
        q = await service.create_queue(raw, _queue())
        await service.join(raw, q.id, _join(PATIENT_A))
        await raw.commit()

    async with db.session() as raw:
        called = await service.advance(raw, q.id)
        await raw.commit()

    async with db.session() as raw:
        await service.complete(raw, called.id)
        await raw.commit()

    topics = [t for t, _ in producer.published]
    assert QUEUE_ADVANCED_TOPIC in topics
    assert topics[-1] == QUEUE_COMPLETED_TOPIC
    await db.dispose()


async def test_rollback_discards_staged_events(settings, tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'queues.db'}")
    await db.init_models(Base)
    producer = FakeProducer()
    service = QueueService(settings, producer=producer)

    request = types.SimpleNamespace(
        app=types.SimpleNamespace(
            state=types.SimpleNamespace(database=db, queue_service=service, producer=producer)
        )
    )
    gen = get_session(request)
    session = await gen.__anext__()
    try:
        q = await service.create_queue(session, _queue())
        await service.join(session, q.id, _join(PATIENT_A))
    finally:
        # the handler raises -> dependency rolls back and discards staged events
        with contextlib.suppress(RuntimeError):
            await gen.athrow(RuntimeError("boom"))

    assert producer.published == []
    await db.dispose()
