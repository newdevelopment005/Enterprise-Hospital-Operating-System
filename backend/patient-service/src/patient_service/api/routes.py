"""REST API for the patient-service.

Endpoints under ``/api/v1/patients`` return the standard EHOS envelope. All
mutations require an authenticated actor (extracted later by the gateway); the
service is registered behind the API gateway which injects the OAuth2 token.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from ehos_common.api import NotFoundError, success_response
from ehos_common.outbox import Outbox
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from patient_service.dto.schemas import (
    BiometricIn,
    EmergencyContactIn,
    IdentifierIn,
    InsuranceIn,
    MedicalAlertIn,
    MergeResponse,
    PatientSummary,
    PhotoIn,
    RegisterRequest,
    UpdateRequest,
)
from patient_service.entity.models import Patient
from patient_service.service.patient_service import PatientError, PatientService

router = APIRouter(prefix="/api/v1/patients", tags=["patients"])


async def get_session(request: Request) -> AsyncSession:
    async with request.app.state.database.session() as session:
        outbox = Outbox()
        session.info["outbox"] = outbox
        try:
            yield session
            await session.commit()
            # Publish staged events only after the write is durable; events
            # staged for a rolled-back transaction are discarded (no phantom
            # events when the DB commit fails).
            await outbox.flush(getattr(request.app.state, "producer", None))
        except Exception:
            await session.rollback()
            outbox.discard()
            raise


def get_service(request: Request) -> PatientService:
    return request.app.state.patient_service


SvcDep = Annotated[PatientService, Depends(get_service)]


# ================================================================== registration

@router.post("", status_code=201)
async def register(
    data: RegisterRequest,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    patient = await svc.register(session, data)
    return success_response(await svc.get_detail(session, patient.id))


@router.get("")
async def search(
    q: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    include_inactive: bool = False,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    rows, total = await svc.search(session, q=q, limit=limit, offset=offset, include_inactive=include_inactive)
    summary = [PatientSummary(**patient_summary_row(p)) for p in rows]
    return success_response({"patients": summary, "total": total, "limit": limit, "offset": offset})


@router.get("/{patient_id}")
async def get_patient(
    patient_id: str,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    return success_response(await svc.get_detail(session, _uuid(patient_id)))


@router.patch("/{patient_id}")
async def update_patient(
    patient_id: str,
    data: UpdateRequest,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    patient = await svc.update(session, _uuid(patient_id), data)
    return success_response(await svc.get_detail(session, patient.id))


# ================================================================== sub-resources

@router.get("/{patient_id}/timeline")
async def timeline(
    patient_id: str,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    entries = await svc.timeline(session, _uuid(patient_id))
    return success_response(
        [{"id": str(e.id), "event_type": e.event_type, "source": e.source,
          "occurred_at": e.occurred_at, "actor": str(e.actor) if e.actor else None,
          "details": e.details} for e in entries]
    )


@router.post("/{patient_id}/alerts")
async def add_alert(
    patient_id: str,
    data: MedicalAlertIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    alert = await svc.add_alert(session, _uuid(patient_id), data)
    return success_response(_alert_out(alert))


@router.post("/{patient_id}/alerts/{alert_id}/resolve")
async def resolve_alert(
    patient_id: str,
    alert_id: str,
    reason: str | None = Query(default=None, max_length=500),
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    alert = await svc.resolve_alert(session, _uuid(patient_id), _uuid(alert_id), reason)
    if alert is None:
        raise NotFoundError("Alert not found")
    return success_response(_alert_out(alert))


@router.get("/{patient_id}/alerts")
async def list_alerts(
    patient_id: str,
    active_only: bool = True,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    alerts = await svc.list_alerts(session, _uuid(patient_id), active_only=active_only)
    return success_response({"items": [_alert_out(a) for a in alerts], "total": len(alerts)})


@router.post("/{patient_id}/biometrics")
async def enroll_biometric(
    patient_id: str,
    data: BiometricIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    row = await svc.enroll_biometric(session, _uuid(patient_id), data)
    return success_response(_biometric_out(row))


@router.post("/{patient_id}/photo")
async def add_photo(
    patient_id: str,
    data: PhotoIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    photo = await svc.add_photo(session, _uuid(patient_id), data)
    return success_response(_photo_out(photo))


@router.post("/{patient_id}/insurance")
async def add_insurance(
    patient_id: str,
    data: InsuranceIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    row = await svc.add_insurance(session, _uuid(patient_id), data)
    return success_response(_insurance_out(row))


@router.post("/{patient_id}/identifiers")
async def add_identifier(
    patient_id: str,
    data: IdentifierIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    row = await svc.add_identifier(session, _uuid(patient_id), data)
    return success_response(_identifier_out(row))


@router.post("/{patient_id}/emergency-contact")
async def add_emergency_contact(
    patient_id: str,
    data: EmergencyContactIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    pid = _uuid(patient_id)
    await svc.get_detail(session, pid)  # validates existence
    patient = await session.get(Patient, pid)
    patient.emergency_contact = data.model_dump()
    await svc._timeline(session, pid, "UPDATED", None, {"fields": ["emergency_contact"]})  # noqa: SLF001
    return success_response(await svc.get_detail(session, pid))


# ================================================================== merge

@router.post("/merge")
async def merge_patients(
    survivor_id: str,
    duplicate_id: str,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    result = await svc.merge(session, _uuid(survivor_id), _uuid(duplicate_id))
    return success_response(MergeResponse(**result))


# ================================================================== helpers

def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise PatientError("INVALID_ID", f"Invalid identifier: {value}", 422) from exc


def patient_summary_row(p) -> dict:
    return {
        "id": str(p.id),
        "patient_number": p.patient_number,
        "mrn": p.mrn,
        "first_name": p.first_name,
        "last_name": p.last_name,
        "other_names": p.other_names,
        "date_of_birth": p.date_of_birth,
        "gender": p.gender,
        "nationality": p.nationality,
        "biometrics_ready": p.biometrics_ready,
        "merged_into_id": str(p.merged_into_id) if p.merged_into_id else None,
        "created_at": p.created_at,
    }


def _alert_out(a) -> dict:
    return {
        "id": str(a.id), "alert_type": a.alert_type, "severity": a.severity, "title": a.title,
        "description": a.description, "active": a.active, "resolved_at": a.resolved_at,
        "created_at": a.created_at,
    }


def _biometric_out(b) -> dict:
    return {
        "id": str(b.id), "modality": b.modality, "enrollment_state": b.enrollment_state,
        "provider": b.provider, "template_ref": b.template_ref, "enrolled_at": b.enrolled_at,
    }


def _photo_out(p) -> dict:
    return {
        "id": str(p.id), "content_type": p.content_type, "object_ref": p.object_ref,
        "is_primary": p.is_primary, "width": p.width, "height": p.height, "taken_at": p.taken_at,
    }


def _insurance_out(i) -> dict:
    return {
        "id": str(i.id), "provider_name": i.provider_name, "provider_code": i.provider_code,
        "card_number": i.card_number, "policy_number": i.policy_number, "member_number": i.member_number,
        "relation_to_subscriber": i.relation_to_subscriber, "coverage_type": i.coverage_type,
        "valid_from": i.valid_from, "valid_to": i.valid_to,
    }


def _identifier_out(idn) -> dict:
    return {
        "id": str(idn.id), "identifier_type": idn.identifier_type,
        "identifier_value": idn.identifier_value, "issuer": idn.issuer,
        "is_primary": idn.is_primary, "valid_from": idn.valid_from, "valid_to": idn.valid_to,
    }