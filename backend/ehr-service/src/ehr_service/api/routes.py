"""REST API for the ehr-service.

All clinical modules are scoped to a patient path: /api/v1/patients/{patient_id}/...
Responses use the standard EHOS envelope {"success": true, "data": ...}.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ehr_service.dto import schemas as dto
from ehr_service.service import ehr_service as svc

router = APIRouter(prefix="/api/v1/ehr", tags=["ehr"])


async def get_session(request: Request) -> AsyncSession:
    async with request.app.state.database.session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as err:
        raise svc.EhrError("INVALID_UUID", f"'{value}' is not a valid UUID", 400) from err


def _s(request: Request) -> svc.EhrService:
    return request.app.state.ehr_service


def _ok(data, status_code: int = 200) -> dict:
    return {"success": True, "data": data, "statusCode": status_code}


# --- encounters ---------------------------------------------------------------


@router.post("/patients/{patient_id}/encounters", status_code=status.HTTP_201_CREATED)
async def create_encounter(
    patient_id: str, payload: dto.EncounterIn, request: Request, session: AsyncSession = Depends(get_session)
):
    record = await _s(request).open_encounter(session, _uuid(patient_id), payload)
    return _ok(svc.encounter_out(record), status.HTTP_201_CREATED)


@router.get("/patients/{patient_id}/encounters")
async def list_encounters(
    patient_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows, total = await _s(request).list_encounters(session, _uuid(patient_id), limit, offset)
    return _ok({"items": [svc.encounter_out(r) for r in rows], "total": total})


@router.post("/patients/{patient_id}/encounters/{encounter_id}/close")
async def close_encounter(
    patient_id: str, encounter_id: str, request: Request, session: AsyncSession = Depends(get_session)
):
    record = await _s(request).close_encounter(session, _uuid(patient_id), _uuid(encounter_id))
    return _ok(svc.encounter_out(record))


# --- clinical notes (general) -------------------------------------------------


@router.post("/patients/{patient_id}/notes", status_code=status.HTTP_201_CREATED)
async def create_note(
    patient_id: str, payload: dto.NoteIn, request: Request, session: AsyncSession = Depends(get_session)
):
    record = await _s(request).create_note(session, _uuid(patient_id), payload)
    return _ok(svc.note_out(record), status.HTTP_201_CREATED)


@router.get("/patients/{patient_id}/notes")
async def list_notes(
    patient_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    note_type: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows, total = await _s(request).list_notes(session, _uuid(patient_id), note_type, limit, offset)
    return _ok({"items": [svc.note_out(r) for r in rows], "total": total})


@router.get("/patients/{patient_id}/notes/{note_id}")
async def get_note(
    patient_id: str, note_id: str, request: Request, session: AsyncSession = Depends(get_session)
):
    record = await _s(request).get_note(session, _uuid(patient_id), _uuid(note_id))
    return _ok(svc.note_out(record))


@router.patch("/patients/{patient_id}/notes/{note_id}")
async def update_note(
    patient_id: str, note_id: str, payload: dto.NoteIn, request: Request, session: AsyncSession = Depends(get_session)
):
    record = await _s(request).update_note(session, _uuid(patient_id), _uuid(note_id), payload)
    return _ok(svc.note_out(record))


@router.post("/patients/{patient_id}/notes/{note_id}/amend", status_code=status.HTTP_201_CREATED)
async def amend_note(
    patient_id: str,
    note_id: str,
    payload: dto.AmendmentIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    record = await _s(request).amend_note(session, _uuid(patient_id), _uuid(note_id), payload)
    return _ok(svc.amendment_out(record), status.HTTP_201_CREATED)


@router.post("/patients/{patient_id}/notes/{note_id}/sign")
async def sign_note(
    patient_id: str,
    note_id: str,
    request: Request,
    signed_by: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    record = await _s(request).sign_note(session, _uuid(patient_id), _uuid(note_id), signed_by)
    return _ok(svc.note_out(record))


@router.get("/patients/{patient_id}/notes/{note_id}/versions")
async def list_versions(
    patient_id: str, note_id: str, request: Request, session: AsyncSession = Depends(get_session)
):
    rows = await _s(request).list_versions(session, _uuid(patient_id), _uuid(note_id))
    return _ok({"items": [svc.version_out(r) for r in rows], "total": len(rows)})


@router.get("/patients/{patient_id}/notes/{note_id}/amendments")
async def list_amendments(
    patient_id: str, note_id: str, request: Request, session: AsyncSession = Depends(get_session)
):
    rows = await _s(request).list_amendments(session, _uuid(patient_id), _uuid(note_id))
    return _ok({"items": [svc.amendment_out(r) for r in rows], "total": len(rows)})


# --- typed notes: SOAP / progress / discharge ----------------------------------


@router.post("/patients/{patient_id}/soap", status_code=status.HTTP_201_CREATED)
async def create_soap(
    patient_id: str, payload: dto.SOAPNoteIn, request: Request, session: AsyncSession = Depends(get_session)
):
    record = await _s(request).create_soap_note(session, _uuid(patient_id), payload)
    return _ok(svc.note_out(record), status.HTTP_201_CREATED)


@router.post("/patients/{patient_id}/progress-notes", status_code=status.HTTP_201_CREATED)
async def create_progress(
    patient_id: str, payload: dto.ProgressNoteIn, request: Request, session: AsyncSession = Depends(get_session)
):
    record = await _s(request).create_progress_note(session, _uuid(patient_id), payload)
    return _ok(svc.note_out(record), status.HTTP_201_CREATED)


@router.post("/patients/{patient_id}/discharge-summary", status_code=status.HTTP_201_CREATED)
async def create_discharge(
    patient_id: str, payload: dto.DischargeSummaryIn, request: Request, session: AsyncSession = Depends(get_session)
):
    record = await _s(request).create_discharge_summary(session, _uuid(patient_id), payload)
    return _ok(svc.note_out(record), status.HTTP_201_CREATED)


# --- vitals -------------------------------------------------------------------


@router.post("/patients/{patient_id}/vitals", status_code=status.HTTP_201_CREATED)
async def record_vitals(
    patient_id: str, request: Request, session: AsyncSession = Depends(get_session)
):
    body = await request.json()
    if isinstance(body, list):
        payload = dto.VitalBatchIn(readings=[dto.VitalIn(**r) for r in body])
    else:
        payload = dto.VitalIn(**body)
    records = await _s(request).record_vitals(session, _uuid(patient_id), payload)
    return _ok({"items": [svc.vital_out(r) for r in records], "count": len(records)}, status.HTTP_201_CREATED)


@router.get("/patients/{patient_id}/vitals")
async def list_vitals(
    patient_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    vital_type: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows, total = await _s(request).list_vitals(session, _uuid(patient_id), vital_type, limit, offset)
    return _ok({"items": [svc.vital_out(r) for r in rows], "total": total})


# --- diagnoses ----------------------------------------------------------------


@router.post("/patients/{patient_id}/diagnoses", status_code=status.HTTP_201_CREATED)
async def add_diagnosis(
    patient_id: str, payload: dto.DiagnosisIn, request: Request, session: AsyncSession = Depends(get_session)
):
    record = await _s(request).add_diagnosis(session, _uuid(patient_id), payload)
    return _ok(svc.diagnosis_out(record), status.HTTP_201_CREATED)


@router.get("/patients/{patient_id}/diagnoses")
async def list_diagnoses(
    patient_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    diagnoses_status: str | None = Query(default=None, alias="status"),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows, total = await _s(request).list_diagnoses(session, _uuid(patient_id), diagnoses_status, limit, offset)
    return _ok({"items": [svc.diagnosis_out(r) for r in rows], "total": total})


@router.post("/patients/{patient_id}/diagnoses/{diagnosis_id}/resolve")
async def resolve_diagnosis(
    patient_id: str,
    diagnosis_id: str,
    payload: dto.DiagnosisResolveIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    record = await _s(request).resolve_diagnosis(session, _uuid(patient_id), _uuid(diagnosis_id), payload)
    return _ok(svc.diagnosis_out(record))


# --- medications --------------------------------------------------------------


@router.post("/patients/{patient_id}/medications", status_code=status.HTTP_201_CREATED)
async def add_medication(
    patient_id: str, payload: dto.MedicationIn, request: Request, session: AsyncSession = Depends(get_session)
):
    record = await _s(request).add_medication(session, _uuid(patient_id), payload)
    return _ok(svc.medication_out(record), status.HTTP_201_CREATED)


@router.get("/patients/{patient_id}/medications")
async def list_medications(
    patient_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    medications_status: str | None = Query(default=None, alias="status"),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows, total = await _s(request).list_medications(session, _uuid(patient_id), medications_status, limit, offset)
    return _ok({"items": [svc.medication_out(r) for r in rows], "total": total})


@router.patch("/patients/{patient_id}/medications/{medication_id}")
async def update_medication(
    patient_id: str,
    medication_id: str,
    payload: dto.MedicationUpdateIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    record = await _s(request).update_medication(session, _uuid(patient_id), _uuid(medication_id), payload)
    return _ok(svc.medication_out(record))


# --- orders -------------------------------------------------------------------


@router.post("/patients/{patient_id}/orders", status_code=status.HTTP_201_CREATED)
async def add_order(
    patient_id: str, payload: dto.ClinicalOrderIn, request: Request, session: AsyncSession = Depends(get_session)
):
    record = await _s(request).add_order(session, _uuid(patient_id), payload)
    return _ok(svc.order_out(record), status.HTTP_201_CREATED)


@router.get("/patients/{patient_id}/orders")
async def list_orders(
    patient_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    order_type: str | None = Query(default=None),
    orders_status: str | None = Query(default=None, alias="status"),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows, total = await _s(request).list_orders(session, _uuid(patient_id), order_type, orders_status, limit, offset)
    return _ok({"items": [svc.order_out(r) for r in rows], "total": total})


@router.patch("/patients/{patient_id}/orders/{order_id}")
async def update_order(
    patient_id: str,
    order_id: str,
    payload: dto.ClinicalOrderUpdateIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    record = await _s(request).update_order(session, _uuid(patient_id), _uuid(order_id), payload)
    return _ok(svc.order_out(record))


# --- allergies ----------------------------------------------------------------


@router.post("/patients/{patient_id}/allergies", status_code=status.HTTP_201_CREATED)
async def add_allergy(
    patient_id: str, payload: dto.AllergyIn, request: Request, session: AsyncSession = Depends(get_session)
):
    record = await _s(request).add_allergy(session, _uuid(patient_id), payload)
    return _ok(svc.allergy_out(record), status.HTTP_201_CREATED)


@router.get("/patients/{patient_id}/allergies")
async def list_allergies(
    patient_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    allergies_status: str | None = Query(default=None, alias="status"),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows, total = await _s(request).list_allergies(session, _uuid(patient_id), allergies_status, limit, offset)
    return _ok({"items": [svc.allergy_out(r) for r in rows], "total": total})


@router.post("/patients/{patient_id}/allergies/{allergy_id}/resolve")
async def resolve_allergy(
    patient_id: str, allergy_id: str, request: Request, session: AsyncSession = Depends(get_session)
):
    record = await _s(request).resolve_allergy(session, _uuid(patient_id), _uuid(allergy_id))
    return _ok(svc.allergy_out(record))


# --- problem list -------------------------------------------------------------


@router.post("/patients/{patient_id}/problems", status_code=status.HTTP_201_CREATED)
async def add_problem(
    patient_id: str, payload: dto.ProblemIn, request: Request, session: AsyncSession = Depends(get_session)
):
    record = await _s(request).add_problem(session, _uuid(patient_id), payload)
    return _ok(svc.problem_out(record), status.HTTP_201_CREATED)


@router.get("/patients/{patient_id}/problems")
async def list_problems(
    patient_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    problems_status: str | None = Query(default=None, alias="status"),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows, total = await _s(request).list_problems(session, _uuid(patient_id), problems_status, limit, offset)
    return _ok({"items": [svc.problem_out(r) for r in rows], "total": total})


@router.post("/patients/{patient_id}/problems/{problem_id}/resolve")
async def resolve_problem(
    patient_id: str, problem_id: str, request: Request, session: AsyncSession = Depends(get_session)
):
    record = await _s(request).resolve_problem(session, _uuid(patient_id), _uuid(problem_id))
    return _ok(svc.problem_out(record))


# --- medical history ----------------------------------------------------------


@router.post("/patients/{patient_id}/medical-history", status_code=status.HTTP_201_CREATED)
async def add_medical_history(
    patient_id: str, payload: dto.MedicalHistoryIn, request: Request, session: AsyncSession = Depends(get_session)
):
    record = await _s(request).add_medical_history(session, _uuid(patient_id), payload)
    return _ok(svc.medical_history_out(record), status.HTTP_201_CREATED)


@router.get("/patients/{patient_id}/medical-history")
async def list_medical_history(
    patient_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    history_type: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows, total = await _s(request).list_medical_history(session, _uuid(patient_id), history_type, limit, offset)
    return _ok({"items": [svc.medical_history_out(r) for r in rows], "total": total})


# --- timeline & chart ---------------------------------------------------------


@router.get("/patients/{patient_id}/timeline")
async def get_timeline(
    patient_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    limit: int | None = Query(default=None, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    rows, total = await _s(request).get_timeline(session, _uuid(patient_id), limit, offset)
    return _ok({"items": [svc.timeline_out(r) for r in rows], "total": total})


@router.get("/patients/{patient_id}/chart")
async def get_chart(
    patient_id: str, request: Request, session: AsyncSession = Depends(get_session)
):
    chart = await _s(request).get_chart(session, _uuid(patient_id))
    return _ok(chart)