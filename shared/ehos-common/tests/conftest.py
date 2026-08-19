"""Shared fixtures + in-memory transport fakes for event-bus tests."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest

from ehos_common import EventRegistry
from ehos_common.worker import Record


def _ts() -> str:
    return datetime.now(UTC).isoformat()


def _payl(event_type: str) -> dict:
    u = lambda: str(uuid.uuid4())  # noqa: E731
    base = {
        "PatientRegistered": {"patientId": u(), "mrn": "MRN-2026-0001", "registeredAt": _ts()},
        "PatientUpdated": {"patientId": u(), "occurredAt": _ts(), "fields": ["phone"]},
        "PatientMerged": {"patientId": u(), "mergedId": u(), "occurredAt": _ts(), "duplicateMrn": "MRN-2026-0002"},
        "PatientDeactivated": {"patientId": u(), "occurredAt": _ts(), "mergedInto": u()},
        "ConfigurationUpdated": {"configKey": "billing.surcharge", "value": 0.05},
        "AppointmentCreated": {
            "appointmentId": u(),
            "patientId": u(),
            "providerId": u(),
            "startAt": _ts(),
            "endAt": _ts(),
            "status": "SCHEDULED",
        },
        "LabOrdered": {
            "labOrderId": u(),
            "patientId": u(),
            "ordererId": u(),
            "panel": ["CBC", "LFT"],
            "priority": "ROUTINE",
            "orderedAt": _ts(),
        },
        "MedicationDispensed": {
            "dispenseId": u(),
            "prescriptionId": u(),
            "patientId": u(),
            "medicationCode": "PARA-500",
            "quantity": 20,
            "unit": "TABLET",
            "dispensedAt": _ts(),
            "dispensedBy": u(),
        },
        "InventoryUpdated": {
            "itemId": u(),
            "sku": "INV-01",
            "delta": -5,
            "newLevel": 12,
            "reorderPoint": 10,
            "updatedAt": _ts(),
            "updatedBy": u(),
        },
        "BillGenerated": {
            "invoiceId": u(),
            "patientId": u(),
            "billNumber": "BL-1001",
            "currency": "USD",
            "totalAmount": 120.0,
            "lineItemCount": 2,
            "generatedAt": _ts(),
            "status": "ISSUED",
        },
        "PayrollCompleted": {
            "runId": u(),
            "periodFrom": "2026-08-01",
            "periodTo": "2026-08-15",
            "employeeId": u(),
            "netPay": 3200.0,
            "currency": "USD",
            "completedAt": _ts(),
            "status": "COMPLETED",
        },
        "EmergencyTriggered": {
            "emergencyId": u(),
            "patientId": u(),
            "severity": "HIGH",
            "location": "ER-01",
            "triggeredAt": _ts(),
            "status": "ACTIVE",
        },
        "KnowledgeDocumentIngested": {
            "documentId": u(),
            "docType": "GUIDELINE",
            "title": "Hand Hygiene",
            "wordCount": 320,
            "ingestedAt": _ts(),
        },
        "AIRequestCreated": {"requestId": u(), "contextType": "CHAT", "userId": None, "status": "PROCESSING"},
        "AIResponseGenerated": {"requestId": u(), "model": "mock", "latencyMs": 43, "status": "OK"},
        "PredictionGenerated": {
            "predictionKey": "patient-inflow.ward.er",
            "entityType": "patient-inflow",
            "entityId": "ward.er",
            "horizon": "7d",
            "generatedAt": _ts(),
        },
    }
    return dict(base.get(event_type, {}))


def make_envelope(
    event_type: str = "PatientRegistered",
    *,
    event_version: str = "1",
    drop: list[str] | None = None,
    **payload_overrides,
) -> dict:
    payload = _payl(event_type)
    payload.update(payload_overrides)
    envelope = {
        "eventId": str(uuid.uuid4()),
        "eventType": event_type,
        "eventVersion": event_version,
        "timestamp": _ts(),
        "source": "test-source",
        "correlationId": None,
        "userId": None,
        "payload": payload,
    }
    for key in drop or []:
        if key in envelope:
            envelope.pop(key)
        elif key in envelope["payload"]:
            envelope["payload"].pop(key)
    return envelope


@pytest.fixture
def registry() -> EventRegistry:
    return EventRegistry()


@pytest.fixture
def make_record():
    def _make(
        envelope,
        *,
        topic: str | None = None,
        headers: list[tuple[str, str]] | None = None,
        raw: str | None = None,
    ) -> Record:
        value = raw if raw is not None else (envelope if isinstance(envelope, str) else json.dumps(envelope))
        if topic is None:
            topic = "clinical.patient.registered" if isinstance(envelope, dict) else "unknown.topic"
        return Record(topic=topic, value=value, headers=headers, partition=0, offset=7)

    return _make


class FakePublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict, list[tuple[str, str]] | None]] = []

    async def publish_envelope(self, topic: str, envelope: dict, headers: list[tuple[str, str]] | None = None) -> None:
        self.published.append((topic, envelope, headers))


class FakeConsumer:
    """Async-iterable queue of records with a recording commit().

    Drains records (no replay); ``eof`` is True once exhausted so the processor
    loop can exit in tests (real Kafka consumers never EOF).
    """

    def __init__(self, records: list[Record] | None = None) -> None:
        self.records = list(records or [])
        self.commits = 0
        self.eof = False

    def __aiter__(self):
        return self

    async def __anext__(self) -> Record:
        try:
            return self.records.pop(0)
        except IndexError as exc:
            self.eof = True
            raise StopAsyncIteration from exc

    async def commit(self) -> None:
        self.commits += 1


@pytest.fixture
def publisher() -> FakePublisher:
    return FakePublisher()


async def fake_ok_handler(envelope: dict, *, record: Record) -> None:
    return None