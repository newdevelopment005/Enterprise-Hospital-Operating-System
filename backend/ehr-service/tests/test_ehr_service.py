"""Tests for the ehr-service clinical modules.

Covers encounters, SOAP / progress / discharge / clinical notes (versioning &
amendments), vitals, diagnoses, medications, orders, allergies, problem list,
medical history, clinical timeline and the aggregate patient chart.
"""

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from ehr_service.dto import schemas as dto
from ehr_service.entity.models import (
    ClinicalTimelineEvent,
    Medication,
)
from ehr_service.service.ehr_service import EhrError, _as_aware

PID = uuid.UUID("11111111-1111-1111-1111-111111111111")
AUTHOR = uuid.UUID("22222222-2222-2222-2222-222222222222")


async def test_open_and_close_encounter(service, session):
    enc = await service.open_encounter(
        session,
        PID,
        dto.EncounterIn(encounter_type="OUTPATIENT", reason="fever and cough", visit_number="V-001"),
    )
    await session.commit()
    assert enc.patient_id == PID
    assert enc.status == "OPEN"

    rows, total = await service.list_encounters(session, PID)
    assert total == 1 and rows[0].visit_number == "V-001"

    closed = await service.close_encounter(session, PID, enc.id)
    assert closed.status == "CLOSED"
    assert closed.end_time is not None


async def test_create_soap_note_structure(service, session):
    note = await service.create_soap_note(
        session,
        PID,
        dto.SOAPNoteIn(
            subjective="cough x4 days",
            objective="t 38.2C, HR 96",
            assessment="URTI",
            plan="rest and fluids",
            author_id=str(AUTHOR),
        ),
    )
    await session.commit()
    assert note.note_type == "SOAP"
    assert note.content_struct["objective"] == "t 38.2C, HR 96"
    assert "SUBJECTIVE: cough x4 days" in note.content
    assert "PLAN: rest and fluids" in note.content


async def test_progress_and_discharge_notes(service, session):
    progress = await service.create_progress_note(
        session, PID, dto.ProgressNoteIn(content="improving", author_id=str(AUTHOR))
    )
    discharge = await service.create_discharge_summary(
        session,
        PID,
        dto.DischargeSummaryIn(
            admission_date=__import__("datetime").date(2026, 1, 1),
            discharge_date=__import__("datetime").date(2026, 1, 5),
            admitting_diagnosis="Pneumonia",
            discharge_diagnosis="Pneumonia, resolved",
            summary="Discharged stable.",
            follow_up_plan="review in 2 weeks",
            author_id=str(AUTHOR),
        ),
    )
    await session.commit()
    assert progress.note_type == "PROGRESS"
    assert discharge.note_type == "DISCHARGE"
    assert discharge.content_struct["discharge_diagnosis"] == "Pneumonia, resolved"


async def test_note_update_creates_version_and_sign(service, session):
    note = await service.create_note(
        session, PID, dto.NoteIn(note_type="CONSULT", content="v1", author_id=str(AUTHOR))
    )
    await session.commit()
    updated = await service.update_note(
        session,
        PID,
        note.id,
        dto.NoteIn(note_type="CONSULT", content="v2", author_id=str(AUTHOR), change_reason="typo fix"),
    )
    await session.commit()
    assert updated.version == 2

    versions = await service.list_versions(session, PID, note.id)
    assert len(versions) == 1
    assert versions[0].version_no == 1 and versions[0].content == "v1"

    amendment = await service.amend_note(
        session, PID, note.id, dto.AmendmentIn(amendment="see attached", author_id=str(AUTHOR))
    )
    await session.commit()
    amendments = await service.list_amendments(session, PID, note.id)
    assert [a.id for a in amendments] == [amendment.id]

    signed = await service.sign_note(session, PID, note.id, None)
    assert signed.approval_status == "SIGNED"

    with pytest.raises(EhrError) as exc:
        await service.update_note(
            session, PID, note.id, dto.NoteIn(note_type="CONSULT", content="v3", author_id=str(AUTHOR))
        )
    assert exc.value.status_code == 409


async def test_notes_filter_by_type(service, session):
    await service.create_soap_note(
        session,
        PID,
        dto.SOAPNoteIn(subjective="s", objective="o", assessment="a", plan="p", author_id=str(AUTHOR)),
    )
    await service.create_note(session, PID, dto.NoteIn(note_type="AI_DRAFT", content="ai", author_id=str(AUTHOR)))
    await session.commit()
    soaps, total = await service.list_notes(session, PID, note_type="SOAP")
    assert total == 1 and soaps[0].note_type == "SOAP"


async def test_vitals_single_and_batch(service, session):
    single = await service.record_vitals(
        session, PID, dto.VitalIn(vital_type="HR", value_numeric=88, unit="bpm")
    )
    batch = await service.record_vitals(
        session,
        PID,
        dto.VitalBatchIn(
            readings=[
                dto.VitalIn(vital_type="TEMP", value_numeric=38.2, unit="C"),
                dto.VitalIn(vital_type="BP", value_text="120/80"),
            ]
        ),
    )
    await session.commit()
    assert len(single) == 1 and len(batch) == 2
    rows, total = await service.list_vitals(session, PID)
    assert total == 3
    bp = next(r for r in rows if r.vital_type == "BP")
    assert bp.value_text == "120/80"


async def test_diagnoses_add_list_resolve(service, session):
    enc = await service.open_encounter(session, PID, dto.EncounterIn(encounter_type="OUTPATIENT"))
    await session.commit()
    diag = await service.add_diagnosis(
        session,
        PID,
        dto.DiagnosisIn(
            diagnosis_code="J06.9",
            description="Acute URTI",
            diagnosed_by=str(AUTHOR),
            encounter_id=str(enc.id),
        ),
    )
    await session.commit()
    rows, total = await service.list_diagnoses(session, PID)
    assert total == 1 and rows[0].diagnosis_code == "J06.9"

    resolved = await service.resolve_diagnosis(session, PID, diag.id, dto.DiagnosisResolveIn())
    assert resolved.status == "RESOLVED"
    with pytest.raises(EhrError):
        await service.resolve_diagnosis(session, PID, diag.id, dto.DiagnosisResolveIn())


async def test_medications_add_discontinue(service, session):
    med = await service.add_medication(
        session,
        PID,
        dto.MedicationIn(
            medication_name="Amoxicillin",
            strength="500 mg",
            route="ORAL",
            frequency="TID",
            indication="URTI",
        ),
    )
    await session.commit()
    assert med.status == "ACTIVE"

    stopped = await service.update_medication(
        session, PID, med.id, dto.MedicationUpdateIn(status="DISCONTINUED")
    )
    assert stopped.status == "DISCONTINUED" and stopped.discontinued_at is not None

    rows, total = await service.list_medications(session, PID, status="ACTIVE")
    assert total == 0
    all_rows, all_total = await service.list_medications(session, PID)
    assert all_total == 1


async def test_orders_add_complete(service, session):
    order = await service.add_order(
        session,
        PID,
        dto.ClinicalOrderIn(order_type="LAB", description="FBC", priority="STAT"),
    )
    await session.commit()
    assert order.status == "REQUESTED"

    done = await service.update_order(
        session, PID, order.id, dto.ClinicalOrderUpdateIn(status="COMPLETED", result_summary="normal")
    )
    assert done.status == "COMPLETED" and done.completed_at is not None
    rows, total = await service.list_orders(session, PID, order_type="LAB")
    assert total == 1


async def test_allergies_duplicate_conflict_and_resolve(service, session):
    await service.add_allergy(
        session, PID, dto.AllergyIn(allergen="Penicillin", allergen_type="DRUG", severity="HIGH")
    )
    await session.commit()
    with pytest.raises(EhrError) as exc:
        await service.add_allergy(
            session, PID, dto.AllergyIn(allergen="Penicillin", allergen_type="DRUG", severity="LOW")
        )
    assert exc.value.status_code == 409
    await session.rollback()

    rows, total = await service.list_allergies(session, PID)
    assert total == 1
    resolved = await service.resolve_allergy(session, PID, rows[0].id)
    assert resolved.status == "RESOLVED"


async def test_problem_list_add_resolve(service, session):
    problem = await service.add_problem(
        session,
        PID,
        dto.ProblemIn(problem="Hypertension", diagnosis_code="I10", severity="MEDIUM"),
    )
    await session.commit()
    rows, total = await service.list_problems(session, PID)
    assert total == 1 and rows[0].problem == "Hypertension"

    resolved = await service.resolve_problem(session, PID, problem.id)
    assert resolved.status == "RESOLVED"
    assert resolved.resolved_date is not None


async def test_medical_history(service, session):
    await service.add_medical_history(
        session,
        PID,
        dto.MedicalHistoryIn(history_type="SURGICAL", description="Appendectomy 2019", facility="St Mary"),
    )
    await session.commit()
    rows, total = await service.list_medical_history(session, PID)
    assert total == 1 and rows[0].history_type == "SURGICAL"
    typed, typed_total = await service.list_medical_history(session, PID, history_type="FAMILY")
    assert typed_total == 0


async def test_timeline_aggregates_all_modules(service, session):
    enc = await service.open_encounter(session, PID, dto.EncounterIn(encounter_type="ED", reason="chest pain"))
    await service.create_soap_note(
        session,
        PID,
        dto.SOAPNoteIn(subjective="s", objective="o", assessment="a", plan="p", author_id=str(AUTHOR)),
    )
    await service.record_vitals(session, PID, dto.VitalIn(vital_type="HR", value_numeric=100, unit="bpm"))
    await service.add_diagnosis(
        session,
        PID,
        dto.DiagnosisIn(
            diagnosis_code="R07.9", description="Chest pain", diagnosed_by=str(AUTHOR), encounter_id=str(enc.id)
        ),
    )
    await service.add_medication(session, PID, dto.MedicationIn(medication_name="Aspirin", route="ORAL"))
    await service.add_order(session, PID, dto.ClinicalOrderIn(order_type="IMAGING", description="CXR"))
    await service.add_allergy(session, PID, dto.AllergyIn(allergen="Latex", allergen_type="ENVIRONMENT"))
    await service.add_problem(session, PID, dto.ProblemIn(problem="Chest pain"))
    await service.add_medical_history(session, PID, dto.MedicalHistoryIn(history_type="PAST_MEDICAL", description="DM"))
    await session.commit()

    events, total = await service.get_timeline(session, PID)
    event_types = {e.event_type for e in events}
    assert "ENCOUNTER_OPENED" in event_types
    assert "NOTE_CREATED" in event_types
    assert "VITALS_RECORDED" in event_types
    assert "DIAGNOSIS_ADDED" in event_types
    assert "MEDICATION_ORDERED" in event_types
    assert "ORDER_REQUESTED" in event_types
    assert "ALLERGY_ADDED" in event_types
    assert "PROBLEM_ADDED" in event_types
    assert "HISTORY_RECORDED" in event_types


async def test_chart_contains_all_sections(service, session):
    enc = await service.open_encounter(session, PID, dto.EncounterIn(encounter_type="OUTPATIENT"))
    await service.create_soap_note(
        session,
        PID,
        dto.SOAPNoteIn(subjective="s", objective="o", assessment="a", plan="p", author_id=str(AUTHOR)),
    )
    await service.record_vitals(session, PID, dto.VitalIn(vital_type="HR", value_numeric=80, unit="bpm"))
    await service.add_diagnosis(
        session,
        PID,
        dto.DiagnosisIn(
            diagnosis_code="A00", description="Cholera", diagnosed_by=str(AUTHOR), encounter_id=str(enc.id)
        ),
    )
    await service.add_medication(session, PID, dto.MedicationIn(medication_name="ORS", route="ORAL"))
    await service.add_order(session, PID, dto.ClinicalOrderIn(order_type="LAB", description="Stool"))
    await service.add_allergy(session, PID, dto.AllergyIn(allergen="Eggs", allergen_type="FOOD"))
    await service.add_problem(session, PID, dto.ProblemIn(problem="Diarrhoea"))
    await service.add_medical_history(session, PID, dto.MedicalHistoryIn(history_type="OTHER", description="vaccines"))
    await session.commit()

    chart = await service.get_chart(session, PID)
    expected = {
        "encounters",
        "notes",
        "vitals",
        "diagnoses",
        "medications",
        "orders",
        "allergies",
        "problems",
        "medical_history",
        "treatments",
        "care_plans",
        "referrals",
    }
    assert expected <= set(chart["sections"].keys())
    assert chart["sections"]["vitals"]["count"] == 1
    assert chart["sections"]["notes"]["count"] == 1


async def test_own_scope_prevents_cross_patient_read(service, session):
    other = uuid.UUID("99999999-9999-9999-9999-999999999999")
    note = await service.create_note(
        session, PID, dto.NoteIn(note_type="CONSULT", content="secret", author_id=str(AUTHOR))
    )
    await session.commit()
    with pytest.raises(EhrError) as exc:
        await service.get_note(session, other, note.id)
    assert exc.value.status_code == 404


async def test_z_unknown_patient_returns_404(service, session):
    unknown = uuid.UUID("00000000-0000-0000-0000-000000000000")
    with pytest.raises(EhrError) as exc:
        await service.close_encounter(session, unknown, uuid.uuid4())
    assert exc.value.status_code == 404


# --- DTO validation ------------------------------------------------------------


def test_vitals_require_value():
    with pytest.raises(ValidationError):
        dto.VitalIn(vital_type="HR")


def test_soap_requires_a_section():
    with pytest.raises(ValidationError):
        dto.SOAPNoteIn()


def test_discharge_date_order_enforced():
    with pytest.raises(ValidationError):
        dto.DischargeSummaryIn(
            admission_date=__import__("datetime").date(2026, 5, 1),
            discharge_date=__import__("datetime").date(2026, 1, 1),
            summary="x",
        )


def test_encounter_type_enum():
    with pytest.raises(ValidationError):
        dto.EncounterIn(encounter_type="WALKIN")


def test_medication_route_enum():
    with pytest.raises(ValidationError):
        dto.MedicationIn(medication_name="X", route="TOTAL_PARENTERAL")


async def test_timeline_domain_events_created(service, session):
    await service.add_order(session, PID, dto.ClinicalOrderIn(order_type="BLOOD", description="crossmatch"))
    await session.commit()
    counts = await session.scalar(
        select(func.count(ClinicalTimelineEvent.id)).where(
            ClinicalTimelineEvent.patient_id == PID,
            ClinicalTimelineEvent.event_type == "ORDER_REQUESTED",
        )
    )
    assert counts == 1


# --- misc persistence sanity ---------------------------------------------------


async def test_timestamps_aware_and_consistent(service, session):
    med = await service.add_medication(session, PID, dto.MedicationIn(medication_name="Paracetamol"))
    await session.commit()
    med2 = await session.get(Medication, med.id)
    assert _as_aware(med2.created_at) is not None
    assert med2.prescribed_at.tzinfo is not None