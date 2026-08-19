"""Tests for audit-consumer resilience: a poison-pill message must not break the loop."""

import json
import types

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from audit_service.entity.models import AuditRecord, Base
from audit_service.events.consumer import AuditConsumer
from audit_service.service.audit_service import AuditService


class FakeDatabase:
    def __init__(self, factory):
        self._factory = factory

    def session(self):
        return self._factory()


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield FakeDatabase(factory)
    await engine.dispose()


def _message(value):
    return types.SimpleNamespace(value=value, topic="clinical.patient.registered", partition=0, offset=42)


async def test_malformed_json_is_skipped_and_loop_survives(db):
    consumer = AuditConsumer("localhost:9092", "g", AuditService(), db, consumer=object())
    malformed = _message(b"this is not json {")

    await consumer._process(malformed)  # must not raise

    async with db.session() as session:
        count = (await session.execute(select(func.count()).select_from(AuditRecord))).scalar_one()
    assert count == 0


async def test_valid_event_is_persisted_and_duplicate_ignored(db):
    consumer = AuditConsumer("localhost:9092", "g", AuditService(), db, consumer=object())
    envelope = {
        "eventId": "9ca05ae8-1b3f-4f2b-9e8d-000000000001",
        "eventType": "PatientRegistered",
        "eventVersion": "1",
        "timestamp": "2026-08-18T10:00:00+00:00",
        "source": "patient-service",
        "correlationId": None,
        "userId": None,
        "payload": {
            "patientId": "00000000-0000-0000-0000-000000000001",
            "mrn": "MRN-2026-0001",
            "registeredAt": "2026-08-18T10:00:00+00:00",
        },
    }
    raw = json.dumps(envelope).encode("utf-8")
    await consumer._process(_message(raw))
    await consumer._process(_message(raw))

    async with db.session() as session:
        rows = (await session.execute(select(AuditRecord))).scalars().all()
    assert len(rows) == 1  # duplicate eventId added exactly once
    assert rows[0].event_type == "PatientRegistered"