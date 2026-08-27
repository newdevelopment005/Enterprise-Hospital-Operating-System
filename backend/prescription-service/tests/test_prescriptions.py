"""Tests for prescribing: allergy conflicts, lifecycle, MAR, allergies."""

import contextlib
import types
import uuid

import pytest
from ehos_common.db import Database

from prescription_service.api.routes import get_session
from prescription_service.dto.schemas import (
    AdministrationIn,
    AllergyIn,
    CancelIn,
    ItemIn,
    PrescriptionIn,
)
from prescription_service.entity.models import Base
from prescription_service.service.prescription_service import (
    PRESCRIPTION_CREATED_TOPIC,
    PrescriptionError,
    PrescriptionService,
)

PATIENT = str(uuid.uuid4())
DOCTOR = str(uuid.uuid4())
NURSE = str(uuid.uuid4())
PATIENT_B = str(uuid.uuid4())


class FakeProducer:
    def __init__(self):
        self.published = []

    async def publish(self, topic, event, headers=None) -> None:
        self.published.append((topic, event.envelope()))


def _item(medication: str = "Paracetamol 500mg", **overrides) -> ItemIn:
    payload = {
        "medication": medication,
        "dosage": "1 tablet",
        "frequency": "3 times daily",
        "route": "ORAL",
        "duration_days": 5,
    }
    payload.update(overrides)
    return ItemIn(**payload)


def _rx(**overrides) -> PrescriptionIn:
    payload = {
        "patient_id": PATIENT,
        "prescriber_id": DOCTOR,
        "therapy_type": "ACUTE",
        "items": [_item()],
    }
    payload.update(overrides)
    return PrescriptionIn(**payload)


# ---------------------------------------------------------------- creation & safety

async def test_create_prescription_with_items(session, service):
    rx = await service.create(session, _rx(items=[_item(), _item("Amoxicillin 500mg")]))
    assert rx.status == "ACTIVE"
    assert rx.allergy_checked is True
    detail = await service.get_detail(session, rx.id)
    assert len(detail["items"]) == 2


async def test_duplicate_medication_rejected(session, service):
    with pytest.raises(PrescriptionError) as err:
        await service.create(session, _rx(items=[_item(), _item("paracetamol 500mg")]))
    assert err.value.error_code == "DUPLICATE_MEDICATION"


async def test_allergy_conflict_blocks_prescribing(session, service):
    await service.add_allergy(
        session,
        AllergyIn(
            patient_id=PATIENT, allergen="Penicillin", allergen_type="DRUG",
            severity="SEVERE", reaction="anaphylaxis", recorded_by=NURSE, confirmed=True,
        ),
    )
    with pytest.raises(PrescriptionError) as err:
        await service.create(session, _rx(items=[_item("Penicillin V 500mg")]))
    assert err.value.error_code == "ALLERGY_CONFLICT"
    assert err.value.status_code == 409


async def test_allergy_override_records_conflict(session, service):
    await service.add_allergy(
        session,
        AllergyIn(
            patient_id=PATIENT, allergen="Aspirin", allergen_type="DRUG",
            severity="MODERATE", reaction="rash", recorded_by=NURSE,
        ),
    )
    rx = await service.create(
        session, _rx(items=[_item("Baby Aspirin 75mg")], override_flags=True)
    )
    assert "override" in (rx.audit_reference or "")
    assert rx.allergy_checked is True


async def test_food_allergy_does_not_block_drugs(session, service):
    await service.add_allergy(
        session,
        AllergyIn(patient_id=PATIENT, allergen="Peanut", allergen_type="FOOD", severity="SEVERE", recorded_by=NURSE),
    )
    rx = await service.create(session, _rx())
    assert rx.status == "ACTIVE"


# ---------------------------------------------------------------- lifecycle

async def test_pause_resume_complete(session, service):
    rx = await service.create(session, _rx())
    paused = await service.set_status(session, rx.id, "PAUSED")
    assert paused.status == "PAUSED"
    resumed = await service.set_status(session, rx.id, "ACTIVE")
    assert resumed.status == "ACTIVE"
    done = await service.set_status(session, rx.id, "COMPLETED")
    assert done.status == "COMPLETED"
    with pytest.raises(PrescriptionError):
        await service.set_status(session, rx.id, "PAUSED")


async def test_cancel_cascades_to_items_and_blocks_mar(session, service):
    rx = await service.create(session, _rx())
    detail = await service.get_detail(session, rx.id)
    item_id = detail["items"][0]["id"]

    cancelled = await service.cancel(session, rx.id, CancelIn(reason="patient discharged"))
    assert cancelled.status == "CANCELLED"

    with pytest.raises(PrescriptionError):
        await service.record_administration(
            session,
            AdministrationIn(prescription_item_id=item_id, administered_by=NURSE),
        )


async def test_discontinue_single_item(session, service):
    rx = await service.create(session, _rx(items=[_item(), _item("Ibuprofen 400mg")]))
    detail = await service.get_detail(session, rx.id)
    first = detail["items"][0]["id"]
    disc = await service.discontinue_item(session, uuid.UUID(first), reason="adverse reaction")
    assert disc.status == "DISCONTINUED"


# ---------------------------------------------------------------- MAR

async def test_record_administration_happy_path(session, service):
    rx = await service.create(session, _rx())
    item_id = (await service.get_detail(session, rx.id))["items"][0]["id"]

    mar = await service.record_administration(
        session,
        AdministrationIn(
            prescription_item_id=item_id,
            administered_by=NURSE,
            batch_number="B-1234",
        ),
    )
    assert mar.status == "GIVEN"
    assert mar.medication == "Paracetamol 500mg"


async def test_refusal_requires_reason(session, service):
    rx = await service.create(session, _rx())
    item_id = (await service.get_detail(session, rx.id))["items"][0]["id"]
    with pytest.raises(PrescriptionError) as err:
        await service.record_administration(
            session,
            AdministrationIn(prescription_item_id=item_id, administered_by=NURSE, mar_status="REFUSED"),
        )
    assert err.value.error_code == "REASON_REQUIRED"


async def test_administration_list_per_patient(session, service):
    rx = await service.create(session, _rx())
    item_id = (await service.get_detail(session, rx.id))["items"][0]["id"]
    await service.record_administration(
        session, AdministrationIn(prescription_item_id=item_id, administered_by=NURSE)
    )
    rows = await service.list_administrations(session, PATIENT)
    assert len(rows) == 1
    rows_b = await service.list_administrations(session, PATIENT_B)
    assert rows_b == []


# ---------------------------------------------------------------- allergies

async def test_add_and_duplicate_allergy(session, service):
    a = await service.add_allergy(
        session,
        AllergyIn(patient_id=PATIENT, allergen="Sulfa drugs", allergen_type="DRUG", severity="MILD", recorded_by=NURSE),
    )
    assert a.severity == "MILD"
    with pytest.raises(PrescriptionError) as err:
        await service.add_allergy(
            session,
            AllergyIn(
                patient_id=PATIENT, allergen="sulfa DRUGS", allergen_type="DRUG",
                severity="MILD", recorded_by=NURSE,
            ),
        )
    assert err.value.error_code == "ALLERGY_EXISTS"


# ---------------------------------------------------------------- outbox events

async def test_events_published_only_after_commit(settings, tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'rx.db'}")
    await db.init_models(Base)
    producer = FakeProducer()
    service = PrescriptionService(settings, producer=producer)

    request = types.SimpleNamespace(
        app=types.SimpleNamespace(
            state=types.SimpleNamespace(database=db, prescription_service=service, producer=producer)
        )
    )
    gen = get_session(request)
    session = await gen.__anext__()
    try:
        await service.create(session, _rx())
        # nothing may hit the bus before the transaction commits
        assert producer.published == []
    finally:
        with contextlib.suppress(StopAsyncIteration):
            await gen.asend(None)  # commit -> flush outbox

    topics = [t for t, _ in producer.published]
    assert topics == [PRESCRIPTION_CREATED_TOPIC]
    await db.dispose()


async def test_rollback_discards_staged_events(settings, tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'rx.db'}")
    await db.init_models(Base)
    producer = FakeProducer()
    service = PrescriptionService(settings, producer=producer)

    request = types.SimpleNamespace(
        app=types.SimpleNamespace(
            state=types.SimpleNamespace(database=db, prescription_service=service, producer=producer)
        )
    )
    gen = get_session(request)
    session = await gen.__anext__()
    try:
        await service.create(session, _rx())
    finally:
        with contextlib.suppress(RuntimeError):
            await gen.athrow(RuntimeError("boom"))

    assert producer.published == []
    await db.dispose()
