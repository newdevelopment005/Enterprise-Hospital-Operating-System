"""Tests for patient registration, validation, search, merge, and timeline."""

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from patient_service.dto.schemas import (
    EmergencyContactIn,
    IdentifierIn,
    InsuranceIn,
    MedicalAlertIn,
    RegisterRequest,
)
from patient_service.entity.models import (
    MedicalAlert,
    Patient,
    PatientBiometric,
    PatientLink,
    PatientTimelineEvent,
)
from patient_service.service.patient_service import PatientError


def build_register(passport: str = "AB1234567", **overrides) -> RegisterRequest:
    base = {
        "first_name": "Jane",
        "last_name": "Doe",
        "date_of_birth": "1990-05-15",
        "gender": "FEMALE",
        "national_identifier": "123-456789-1",
        "emergency_contact": EmergencyContactIn(name="John Doe", relationship="SPOUSE", phone="+255712345678"),
        "identifiers": [
            IdentifierIn(
                identifier_type="PASSPORT",
                identifier_value=passport,
            ),
        ],
        "insurance": InsuranceIn(
            provider_name="NHIF",
            provider_code="NHIF",
            card_number=f"NHIF-{passport[-4:]}",
            relation_to_subscriber="SELF",
            coverage_type="INPATIENT",
        ),
        "alerts": [MedicalAlertIn(alert_type="ALLERGY", severity="HIGH", title="Penicillin allergy")],
    }
    base.update(overrides)
    return RegisterRequest(**base)


# ---------------------------------------------------------------- registration

async def test_register_creates_patient_and_children(session, service):
    patient = await service.register(session, build_register())
    await session.flush()

    assert patient.mrn.startswith("EH")
    assert patient.patient_number.startswith("P")
    assert patient.gender == "FEMALE"
    assert patient.biometrics_ready is False

    timeline = (await session.execute(select(PatientTimelineEvent))).scalars().all()
    assert [t.event_type for t in timeline] == ["REGISTERED"]

    from patient_service.entity.models import PatientIdentifier, PatientInsurance

    identifiers = (await session.execute(select(PatientIdentifier))).scalars().all()
    assert any(i.identifier_type == "PASSPORT" for i in identifiers)

    insurances = (await session.execute(select(PatientInsurance))).scalars().all()
    assert len(insurances) == 1
    assert insurances[0].provider_name == "NHIF"

    alerts = (await session.execute(select(MedicalAlert))).scalars().all()
    assert len(alerts) == 1
    assert alerts[0].title == "Penicillin allergy"


async def test_register_assigns_sequential_mrns(session, service):
    first = await service.register(session, build_register())
    await session.flush()
    second = await service.register(session, build_register(passport="CD2345678", national_identifier="111-222333-4"))
    await session.flush()
    assert int(first.mrn[2:]) + 1 == int(second.mrn[2:])


async def test_register_rejects_duplicate_national_id(session, service):
    await service.register(session, build_register())
    await session.flush()
    with pytest.raises(PatientError) as exc:
        await service.register(session, build_register(passport="EF3456789", first_name="Other"))
        await session.flush()
    assert exc.value.error_code == "DUPLICATE_PATIENT"
    # The existing patient's MRN must never leak in the error message (PHI).
    assert exc.value.message == "A patient with this National ID is already registered."


# ---------------------------------------------------------------- validation

def test_validation_rejects_future_dob():
    with pytest.raises(ValidationError):
        build_register(date_of_birth="2099-01-01")


def test_validation_rejects_bad_nid():
    with pytest.raises(ValidationError):
        build_register(national_identifier="abc!def")


def test_validation_rejects_digit_in_name():
    with pytest.raises(ValidationError):
        build_register(first_name="Jane2")


def test_validation_rejects_bad_passport():
    with pytest.raises(ValidationError):
        RegisterRequest(**{
            "first_name": "A", "last_name": "B",
            "identifiers": [IdentifierIn(identifier_type="PASSPORT", identifier_value="123")],
        })


def test_validation_rejects_bad_phone():
    with pytest.raises(ValidationError):
        RegisterRequest(**{
            "first_name": "A", "last_name": "B",
            "emergency_contact": EmergencyContactIn(name="X", relationship="Y", phone="not-a-phone"),
        })


def test_validation_rejects_bad_insurance_card():
    with pytest.raises(ValidationError):
        build_register().model_copy(update={"insurance": InsuranceIn(
            provider_name="NHIF", card_number="!!invalid!!",
        )})


# ---------------------------------------------------------------- search

async def test_search_by_name_and_mrn(session, service):
    p = await service.register(session, build_register())
    await session.flush()

    rows, total = await service.search(session, q="jane")
    assert total == 1
    assert rows[0].id == p.id

    rows, total = await service.search(session, q=p.mrn)
    assert total == 1

    rows, total = await service.search(session, q="nonexistent")
    assert total == 0


# ---------------------------------------------------------------- update & alerts

async def test_update_patient(session, service):
    p = await service.register(session, build_register())
    await session.flush()
    from patient_service.dto.schemas import UpdateRequest

    updated = await service.update(session, p.id, UpdateRequest(marital_status="MARRIED"))
    await session.flush()
    assert updated.marital_status == "MARRIED"
    assert updated.version == 2


async def test_add_and_resolve_alert(session, service):
    p = await service.register(session, build_register())
    await session.flush()
    alert = await service.add_alert(
        session, p.id, MedicalAlertIn(alert_type="FALL_RISK", severity="CRITICAL", title="Fall risk")
    )
    await session.flush()
    resolved = await service.resolve_alert(session, p.id, alert.id, reason="evaluated")
    await session.flush()
    assert resolved.active is False
    assert resolved.resolved_reason == "evaluated"


# ---------------------------------------------------------------- merge

async def test_merge_rehomes_children_and_deactivates_duplicate(session, service):
    survivor = await service.register(session, build_register())
    await session.flush()
    duplicate = await service.register(
        session, build_register(passport="EF3456789", national_identifier="222-333444-5", first_name="Janet")
    )
    await session.flush()

    result = await service.merge(session, survivor.id, duplicate.id)
    await session.flush()

    assert result["duplicate_deactivated"] is True
    assert result["links_created"] == 1
    assert "alert" in result["duplicate_moved"]

    dup = await session.get(Patient, duplicate.id)
    assert dup.deleted_at is not None
    assert dup.merged_into_id == survivor.id

    links = (await session.execute(select(PatientLink))).scalars().all()
    assert len(links) == 1
    assert links[0].link_type == "SAME_PERSON"


async def test_merge_self_raises(session, service):
    p = await service.register(session, build_register())
    await session.flush()
    with pytest.raises(PatientError) as exc:
        await service.merge(session, p.id, p.id)
    assert exc.value.error_code == "MERGE_SELF"


# ---------------------------------------------------------------- biometrics

async def test_enroll_biometric_sets_ready(session, service):
    p = await service.register(session, build_register())
    await session.flush()
    from patient_service.dto.schemas import BiometricIn

    row = await service.enroll_biometric(
        session, p.id, BiometricIn(modality="FINGERPRINT", enrollment_state="READY", provider="BioSign")
    )
    await session.flush()
    assert row.enrollment_state == "READY"
    fresh = await session.get(Patient, p.id)
    assert fresh.biometrics_ready is True


async def test_biometric_unique_per_modality(session, service):
    p = await service.register(session, build_register())
    await session.flush()
    from patient_service.dto.schemas import BiometricIn

    await service.enroll_biometric(session, p.id, BiometricIn(modality="FACE", enrollment_state="ENROLLED"))
    await session.flush()
    await service.enroll_biometric(session, p.id, BiometricIn(modality="FACE", enrollment_state="READY"))
    await session.flush()
    rows = (await session.execute(select(PatientBiometric).where(PatientBiometric.patient_id == p.id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].enrollment_state == "READY"