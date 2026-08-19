"""Tests for EHR bus publishing (clinical.ehr.record.updated)."""

import uuid

import pytest
from ehos_common.events import DomainEvent
from sqlalchemy import select

from ehr_service.dto import schemas as dto
from ehr_service.entity.models import ClinicalTimelineEvent
from ehr_service.service.ehr_service import EhrService

PID = uuid.UUID("11111111-1111-1111-1111-111111111111")
AUTHOR = uuid.UUID("22222222-2222-2222-2222-222222222222")


class FakeProducer:
    def __init__(self):
        self.published: list[tuple[str, DomainEvent]] = []

    async def publish(self, topic: str, event: DomainEvent, headers=None) -> None:
        self.published.append((topic, event))


@pytest.mark.asyncio
async def test_medical_note_publishes_clinical_record_updated(service, session):
    producer = FakeProducer()
    svc = EhrService(service.settings, producer=producer)
    note = await svc.create_note(
        session,
        PID,
        dto.NoteIn(
            note_type="CONSULT",
            content="patient stable",
            author_id=str(AUTHOR),
            author_role="PHYSICIAN",
        ),
    )
    await session.flush()
    assert len(producer.published) == 1
    topic, event = producer.published[0]
    assert topic == "clinical.ehr.record.updated"
    assert event.event_type == "ClinicalRecordUpdated"
    payload = event.payload
    assert payload["patientId"] == str(PID)
    assert payload["recordType"] == "clinical_note"
    assert payload["recordId"] == str(note.id)
    assert payload["eventType"] == "NOTE_CREATED"
    assert payload["actorId"] == str(AUTHOR)
    assert "occurredAt" in payload


@pytest.mark.asyncio
async def test_no_producer_does_not_fail(service, session):
    svc = EhrService(service.settings)
    await svc.add_diagnosis(
        session,
        PID,
        dto.DiagnosisIn(
            diagnosis_code="J06.9",
            code_system="ICD-10",
            description="URTI",
            type="WORKING",
            encounter_id=str(uuid.uuid4()),
            diagnosed_by=str(uuid.uuid4()),
        ),
    )
    await session.flush()
    rows = await session.scalars(select(ClinicalTimelineEvent).where(ClinicalTimelineEvent.patient_id == PID))
    assert len(list(rows)) == 1


@pytest.mark.asyncio
async def test_event_without_entity_or_actor_conforms_to_registry_schema(service, session):
    from ehos_common.event_registry import EventRegistry

    registry = EventRegistry()
    producer = FakeProducer()
    svc = EhrService(service.settings, producer=producer)
    await svc.record_vitals(
        session,
        PID,
        dto.VitalIn(vital_type="HR", value_numeric=72, unit="bpm"),
    )
    await session.flush()
    assert len(producer.published) == 1
    _, event = producer.published[0]
    assert "recordId" not in event.payload
    assert "actorId" not in event.payload
    registry.validate(event.envelope())
