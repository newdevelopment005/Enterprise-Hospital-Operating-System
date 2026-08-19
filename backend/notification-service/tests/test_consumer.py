"""End-to-end test of event-driven notification delivery.

A PatientRegistered envelope travels the shared EventProcessor pipeline
(validation -> dispatch -> create_and_send) and lands in an adapter. Uses an
in-memory consumer/publisher pair so no broker is needed.
"""

from __future__ import annotations

import json

import pytest
from ehos_common.worker import Record
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from notification_service.entity.models import Base, Notification
from notification_service.events.consumer import NotificationEventProcessor
from notification_service.service.notification_service import NotificationService


class FakeConsumer:
    def __init__(self, records: list[Record]):
        self._records = records
        self.eof = False

    def __aiter__(self):
        return iter(self._records)

    async def commit(self) -> None:
        return None


class FakeProducer:
    def __init__(self):
        self.published = []

    async def publish(self, topic, event, headers=None) -> None:
        self.published.append((topic, event, headers))

    async def publish_envelope(self, topic, envelope, headers=None) -> None:
        self.published.append((topic, envelope, headers))


class RecorderAdapter:
    def __init__(self):
        self.sent = []

    def send(self, *, recipient, subject, body):
        self.sent.append({"recipient": recipient, "subject": subject, "body": body})
        return {"messageId": "m-1"}


def _envelope(payload: dict) -> Record:
    envelope = {
        "eventId": "9ca05ae8-1b3f-4f2b-9e8d-000000000001",
        "eventType": "PatientRegistered",
        "eventVersion": "1",
        "timestamp": "2026-08-18T10:00:00+00:00",
        "source": "patient-service",
        "correlationId": "corr-1",
        "userId": None,
        "payload": payload,
    }
    return Record(topic="clinical.patient.registered", value=json.dumps(envelope))


async def test_patient_registered_event_creates_and_delivers_notification():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    adapter = RecorderAdapter()
    service = NotificationService({"in_app": adapter, "email": adapter})
    producer = FakeProducer()
    record = _envelope(
        {
            "patientId": "11111111-1111-1111-1111-111111111111",
            "mrn": "MRN-2026-0001",
            "firstName": "Ida",
            "lastName": "Potency",
            "registeredAt": "2026-08-18T10:00:00+00:00",
        }
    )

    processor = NotificationEventProcessor(
        bootstrap_servers="unused",
        group_id="test-group",
        service=service,
        session_factory=factory,
        event_routing={
            "PatientRegistered": {
                "create": (lambda p: __import__(
                    "notification_service.dto.schemas", fromlist=["NotificationCreate"]
                ).NotificationCreate(
                    template_key="patient_registered",
                    recipient=p.get("recipient") or "admissions@ehos.example",
                    channel="in_app",
                    variables={"name": f"{p.get('firstName','')} {p.get('lastName','')}".strip()},
                )),
                "defaultRecipient": "admissions@ehos.example",
            }
        },
        producer=producer,
        consumer=FakeConsumer([record]),
    )

    outcome = await processor.processor.process_record(record)

    assert outcome.status == "consumed"
    assert producer.published == []
    async with factory() as session:
        rows = (await session.execute(__import__("sqlalchemy").select(Notification))).scalars().all()
        assert len(rows) == 1
        assert rows[0].recipient == "admissions@ehos.example"
        assert rows[0].channel == "in_app"
        assert rows[0].correlation_id == "corr-1"
    assert adapter.sent == [{"recipient": "admissions@ehos.example", "subject": None, "body": ""}]
    await engine.dispose()


@pytest.mark.asyncio
async def test_redelivered_event_is_idempotent():
    """At-least-once redelivery of the same eventId must not create a duplicate."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    adapter = RecorderAdapter()
    service = NotificationService({"in_app": adapter, "email": adapter})
    producer = FakeProducer()
    record = _envelope(
        {
            "patientId": "11111111-1111-1111-1111-111111111111",
            "mrn": "MRN-2026-0001",
            "firstName": "Ida",
            "lastName": "Potency",
            "registeredAt": "2026-08-18T10:00:00+00:00",
        }
    )

    processor = NotificationEventProcessor(
        bootstrap_servers="unused",
        group_id="test-group",
        service=service,
        session_factory=factory,
        event_routing={
            "PatientRegistered": {
                "create": (lambda p: __import__(
                    "notification_service.dto.schemas", fromlist=["NotificationCreate"]
                ).NotificationCreate(
                    template_key="patient_registered",
                    recipient=p.get("recipient") or "admissions@ehos.example",
                    channel="in_app",
                    variables={"name": f"{p.get('firstName','')} {p.get('lastName','')}".strip()},
                )),
                "defaultRecipient": "admissions@ehos.example",
            }
        },
        producer=producer,
        consumer=FakeConsumer([record]),
    )

    first = await processor.processor.process_record(record)
    second = await processor.processor.process_record(record)

    assert first.status == "consumed"
    assert second.status == "consumed"
    async with factory() as session:
        rows = (await session.execute(__import__("sqlalchemy").select(Notification))).scalars().all()
        assert len(rows) == 1
        assert rows[0].notification_id == record_value_event_id(record)
    assert len(adapter.sent) == 1
    await engine.dispose()


def record_value_event_id(record) -> str:
    return json.loads(record.value)["eventId"]


@pytest.mark.asyncio
async def test_invalid_patient_event_goes_to_dlq():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    adapter = RecorderAdapter()
    service = NotificationService({"in_app": adapter})
    producer = FakeProducer()
    record = _envelope({"patientId": "not-a-uuid", "mrn": "X"})

    processor = NotificationEventProcessor(
        bootstrap_servers="unused",
        group_id="test-group",
        service=service,
        session_factory=factory,
        event_routing={"PatientRegistered": {}},
        producer=producer,
        consumer=FakeConsumer([record]),
    )

    outcome = await processor.processor.process_record(record)

    assert outcome.status == "dlq"
    # permanent schema violation lands straight on the DLQ topic
    assert outcome.dest_topic == "clinical.patient.registered.dlq"
    assert producer.published[0][0] == "clinical.patient.registered.dlq"
    await engine.dispose()