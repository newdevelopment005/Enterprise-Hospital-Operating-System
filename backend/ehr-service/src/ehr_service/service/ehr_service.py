"""Domain service for the ehr-service.

Implements the clinical workflows for every EHR module, all scoped to a single
patient: encounters, SOAP/progress/discharge/clinical notes (with versioning and
amendments), vitals (single + batch), diagnoses, medications, clinical orders,
allergies, problem list, medical history and a source-tagged clinical timeline.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime

from ehos_common.events import DomainEvent, KafkaProducer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ehr_service.configuration import EhrSettings
from ehr_service.dto import schemas as dto
from ehr_service.entity.models import (
    CarePlan,
    ClinicalNote,
    ClinicalNoteAmendment,
    ClinicalNoteVersion,
    ClinicalOrder,
    ClinicalTimelineEvent,
    Diagnosis,
    Encounter,
    MedicalHistory,
    Medication,
    PatientAllergy,
    ProblemListEntry,
    Referral,
    Treatment,
    VitalSign,
)

log = logging.getLogger("ehr-service")


def _now() -> datetime:
    return datetime.now(UTC)


def _name(cls_name: str) -> str:
    return cls_name[0].lower() + "".join(
        "_" + c.lower() if c.isupper() else c for c in cls_name[1:]
    )


def _parse_uuid(value: str | None, field: str) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    try:
        return uuid.UUID(value)
    except ValueError as err:
        raise EhrError("INVALID_UUID", f"{field} is not a valid UUID", 400) from err


def _as_aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _patient_select(model, patient_id: uuid.UUID, order_by: str):
    """Active rows for a patient ordered newest-first."""
    return (
        select(model)
        .where(model.patient_id == patient_id, model.deleted_at.is_(None))
        .order_by(getattr(model, order_by).desc())
    )


class EhrError(Exception):
    """Domain error surfaced as an EHOS-style failure envelope."""

    def __init__(self, error_code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_code = status_code


class EhrService:
    """Clinical workflows over the ehr database."""

    EHR_TOPIC = "clinical.ehr.record.updated"

    def __init__(self, settings: EhrSettings, producer: KafkaProducer | None = None):
        self.settings = settings
        self.producer = producer

    # ------------------------------------------------------------------ helpers

    async def _publish(self, event: ClinicalTimelineEvent) -> None:
        """Publish a clinical record change to the bus (best-effort).

        Publishing must never break the clinical write: failures are logged and
        swallowed so local development without a bus still works.
        """
        if self.producer is None:
            return
        try:
            payload: dict = {
                "patientId": str(event.patient_id),
                "eventType": event.event_type,
                "occurredAt": event.occurred_at.isoformat(),
                "source": event.source,
                "details": event.details or {},
            }
            # Optional fields are omitted (not null) so the payload conforms to
            # the registry schema for ClinicalRecordUpdated — null UUIDs fail
            # validation and would otherwise route the event to the DLQ.
            if event.entity_id:
                payload["recordId"] = str(event.entity_id)
            if event.entity_type:
                payload["recordType"] = event.entity_type
            if event.actor_id:
                payload["actorId"] = str(event.actor_id)
            await self.producer.publish(
                self.EHR_TOPIC,
                DomainEvent(
                    event_type="ClinicalRecordUpdated",
                    source="ehr-service",
                    user_id=str(event.actor_id) if event.actor_id else None,
                    payload=payload,
                ),
            )
        except Exception:  # noqa: BLE001 - publishing must never break the clinical write
            log.exception("failed to publish ClinicalRecordUpdated")

    async def _timeline(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        event_type: str,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        details: dict | None = None,
        source: str = "MANUAL",
    ) -> ClinicalTimelineEvent:
        event = ClinicalTimelineEvent(
            patient_id=patient_id,
            event_type=event_type,
            source=source,
            entity_type=entity_type,
            entity_id=entity_id,
            occurred_at=_now(),
            actor_id=actor_id,
            details=details,
        )
        session.add(event)
        await session.flush()
        await self._publish(event)
        return event

    @staticmethod
    def _limit(settings: EhrSettings, limit: int | None, offset: int | None) -> tuple[int, int]:
        limit = settings.search_limit if limit is None else limit
        limit = max(1, min(limit, settings.search_max_limit))
        return limit, max(0, offset or 0)

    # ------------------------------------------------------------- encounters

    async def open_encounter(
        self, session: AsyncSession, patient_id: uuid.UUID, payload: dto.EncounterIn
    ) -> Encounter:
        encounter = Encounter(
            patient_id=patient_id,
            encounter_type=payload.encounter_type,
            department_id=_parse_uuid(payload.department_id, "department_id"),
            provider_id=_parse_uuid(payload.provider_id, "provider_id"),
            start_time=payload.start_time or _now(),
            end_time=payload.end_time,
            visit_number=payload.visit_number,
            reason=payload.reason,
            status="OPEN",
        )
        session.add(encounter)
        await session.flush()
        await self._timeline(
            session,
            patient_id,
            "ENCOUNTER_OPENED",
            entity_type="encounter",
            entity_id=encounter.id,
            actor_id=encounter.provider_id,
            details={"encounter_type": payload.encounter_type, "visit_number": payload.visit_number},
        )
        return encounter

    async def list_encounters(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[Encounter], int]:
        limit, offset = self._limit(self.settings, limit, offset)
        total = await session.scalar(
            select(func.count(Encounter.id)).where(
                Encounter.patient_id == patient_id, Encounter.deleted_at.is_(None)
            )
        )
        rows = await session.scalars(
            select(Encounter)
            .where(Encounter.patient_id == patient_id, Encounter.deleted_at.is_(None))
            .order_by(Encounter.start_time.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total or 0)

    async def close_encounter(
        self, session: AsyncSession, patient_id: uuid.UUID, encounter_id: uuid.UUID
    ) -> Encounter:
        encounter = await self._get_owned(session, Encounter, patient_id, encounter_id)
        if encounter.status == "CLOSED":
            raise EhrError("ENCOUNTER_CLOSED", "encounter is already closed", 409)
        encounter.status = "CLOSED"
        encounter.end_time = encounter.end_time or _now()
        await self._timeline(session, patient_id, "ENCOUNTER_CLOSED", entity_type="encounter", entity_id=encounter.id)
        return encounter

    # ------------------------------------------------------------------ notes

    @staticmethod
    def _render_note_content(content_struct: dict | None) -> str:
        if not content_struct:
            return ""
        return "\n\n".join(
            f"{label}: {content_struct[section]}"
            for section, label in [
                ("subjective", "SUBJECTIVE"),
                ("objective", "OBJECTIVE"),
                ("assessment", "ASSESSMENT"),
                ("plan", "PLAN"),
            ]
            if content_struct.get(section)
        )

    async def _add_note(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        *,
        note_type: str,
        content: str,
        content_struct: dict | None,
        encounter_id: uuid.UUID | None,
        author_id: uuid.UUID | None,
        author_role: str | None,
        source: str,
    ) -> ClinicalNote:
        note = ClinicalNote(
            patient_id=patient_id,
            encounter_id=encounter_id,
            author_id=author_id,
            author_role=author_role,
            note_type=note_type,
            content=content,
            content_struct=content_struct,
            approval_status="DRAFT",
            source=source,
        )
        session.add(note)
        await session.flush()
        await self._timeline(
            session,
            patient_id,
            "NOTE_CREATED",
            entity_type="clinical_note",
            entity_id=note.id,
            actor_id=author_id,
            details={"note_type": note_type},
            source=source,
        )
        return note

    async def create_note(
        self, session: AsyncSession, patient_id: uuid.UUID, payload: dto.NoteIn
    ) -> ClinicalNote:
        return await self._add_note(
            session,
            patient_id,
            note_type=payload.note_type,
            content=payload.content,
            content_struct=payload.content_struct,
            encounter_id=_parse_uuid(payload.encounter_id, "encounter_id"),
            author_id=_parse_uuid(payload.author_id, "author_id"),
            author_role=payload.author_role,
            source=payload.source or "MANUAL",
        )

    async def create_soap_note(
        self, session: AsyncSession, patient_id: uuid.UUID, payload: dto.SOAPNoteIn
    ) -> ClinicalNote:
        struct = {
            "subjective": payload.subjective,
            "objective": payload.objective,
            "assessment": payload.assessment,
            "plan": payload.plan,
        }
        return await self._add_note(
            session,
            patient_id,
            note_type="SOAP",
            content=self._render_note_content(struct),
            content_struct=struct,
            encounter_id=_parse_uuid(payload.encounter_id, "encounter_id"),
            author_id=_parse_uuid(payload.author_id, "author_id"),
            author_role=payload.author_role,
            source=payload.source or "MANUAL",
        )

    async def create_progress_note(
        self, session: AsyncSession, patient_id: uuid.UUID, payload: dto.ProgressNoteIn
    ) -> ClinicalNote:
        return await self._add_note(
            session,
            patient_id,
            note_type="PROGRESS",
            content=payload.content,
            content_struct=payload.progress_note,
            encounter_id=_parse_uuid(payload.encounter_id, "encounter_id"),
            author_id=_parse_uuid(payload.author_id, "author_id"),
            author_role=payload.author_role,
            source="MANUAL",
        )

    async def create_discharge_summary(
        self, session: AsyncSession, patient_id: uuid.UUID, payload: dto.DischargeSummaryIn
    ) -> ClinicalNote:
        struct = {
            "admission_date": payload.admission_date.isoformat() if payload.admission_date else None,
            "discharge_date": payload.discharge_date.isoformat() if payload.discharge_date else None,
            "admitting_diagnosis": payload.admitting_diagnosis,
            "discharge_diagnosis": payload.discharge_diagnosis,
            "discharge_condition": payload.discharge_condition,
            "medications_on_discharge": payload.medications_on_discharge,
            "follow_up_plan": payload.follow_up_plan,
            "patient_instructions": payload.patient_instructions,
        }
        return await self._add_note(
            session,
            patient_id,
            note_type="DISCHARGE",
            content=payload.summary,
            content_struct=struct,
            encounter_id=_parse_uuid(payload.encounter_id, "encounter_id"),
            author_id=_parse_uuid(payload.author_id, "author_id"),
            author_role=payload.author_role,
            source="MANUAL",
        )

    async def get_note(
        self, session: AsyncSession, patient_id: uuid.UUID, note_id: uuid.UUID
    ) -> ClinicalNote:
        return await self._get_owned(session, ClinicalNote, patient_id, note_id)

    async def list_notes(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        note_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[ClinicalNote], int]:
        limit, offset = self._limit(self.settings, limit, offset)
        query = select(ClinicalNote).where(ClinicalNote.patient_id == patient_id, ClinicalNote.deleted_at.is_(None))
        count_query = select(func.count(ClinicalNote.id)).where(
            ClinicalNote.patient_id == patient_id, ClinicalNote.deleted_at.is_(None)
        )
        if note_type:
            query = query.where(ClinicalNote.note_type == note_type.upper())
            count_query = count_query.where(ClinicalNote.note_type == note_type.upper())
        total = await session.scalar(count_query)
        rows = await session.scalars(
            query.order_by(ClinicalNote.created_at.desc()).limit(limit).offset(offset)
        )
        return list(rows), int(total or 0)

    async def update_note(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        note_id: uuid.UUID,
        payload: dto.NoteIn,
    ) -> ClinicalNote:
        note = await self._get_owned(session, ClinicalNote, patient_id, note_id)
        if note.approval_status in ("SIGNED", "RETRACTED"):
            raise EhrError("NOTE_LOCKED", f"note is {note.approval_status} and cannot be edited", 409)
        session.add(
            ClinicalNoteVersion(
                note_id=note.id,
                version_no=note.version,
                content=note.content,
                content_struct=note.content_struct,
                author_id=note.author_id,
                change_reason=payload.change_reason,
            )
        )
        note.version = (note.version or 0) + 1
        note.content = payload.content
        note.content_struct = payload.content_struct
        await session.flush()
        await self._timeline(
            session,
            patient_id,
            "NOTE_AMENDED",
            entity_type="clinical_note",
            entity_id=note.id,
            actor_id=note.author_id,
            details={"note_type": note.note_type, "new_version": note.version},
        )
        return note

    async def amend_note(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        note_id: uuid.UUID,
        payload: dto.AmendmentIn,
    ) -> ClinicalNoteAmendment:
        note = await self._get_owned(session, ClinicalNote, patient_id, note_id)
        amendment = ClinicalNoteAmendment(
            note_id=note.id,
            author_id=_parse_uuid(payload.author_id, "author_id"),
            amendment=payload.amendment,
            added_at=_now(),
        )
        session.add(amendment)
        await self._timeline(
            session,
            patient_id,
            "NOTE_AMENDED",
            entity_type="clinical_note_amendment",
            entity_id=amendment.id,
            actor_id=amendment.author_id,
        )
        return amendment

    async def sign_note(
        self, session: AsyncSession, patient_id: uuid.UUID, note_id: uuid.UUID, signed_by: str | None
    ) -> ClinicalNote:
        note = await self._get_owned(session, ClinicalNote, patient_id, note_id)
        note.approval_status = "SIGNED"
        note.signed_by = _parse_uuid(signed_by, "signed_by") or note.author_id
        note.signed_at = _now()
        await self._timeline(
            session, patient_id, "NOTE_SIGNED", entity_type="clinical_note", entity_id=note.id
        )
        return note

    async def list_versions(
        self, session: AsyncSession, patient_id: uuid.UUID, note_id: uuid.UUID
    ) -> list[ClinicalNoteVersion]:
        await self._get_owned(session, ClinicalNote, patient_id, note_id)
        rows = await session.scalars(
            select(ClinicalNoteVersion)
            .where(ClinicalNoteVersion.note_id == note_id)
            .order_by(ClinicalNoteVersion.version_no.desc())
        )
        return list(rows)

    async def list_amendments(
        self, session: AsyncSession, patient_id: uuid.UUID, note_id: uuid.UUID
    ) -> list[ClinicalNoteAmendment]:
        await self._get_owned(session, ClinicalNote, patient_id, note_id)
        rows = await session.scalars(
            select(ClinicalNoteAmendment)
            .where(ClinicalNoteAmendment.note_id == note_id)
            .order_by(ClinicalNoteAmendment.added_at.asc())
        )
        return list(rows)

    # ------------------------------------------------------------------- vitals

    @staticmethod
    def _vital_value(payload: dto.VitalIn) -> tuple[float | None, str | None, str | None]:
        if payload.vital_type == "BP":
            return None, payload.value_text or f"{int(payload.value_numeric) if payload.value_numeric else ''}", "mmHg"
        if payload.value_numeric is not None:
            return payload.value_numeric, None, payload.unit
        return None, payload.value_text, payload.unit

    async def record_vitals(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        payload: dto.VitalIn | dto.VitalBatchIn,
    ) -> list[VitalSign]:
        readings = payload.readings if isinstance(payload, dto.VitalBatchIn) else [payload]
        recorded: list[VitalSign] = []
        for reading in readings:
            # batch overrides encounter for all readings unless specified
            enc = reading.encounter_id or (payload.encounter_id if isinstance(payload, dto.VitalBatchIn) else None)
            value_numeric, value_text, unit = self._vital_value(reading)
            vital = VitalSign(
                patient_id=patient_id,
                encounter_id=_parse_uuid(enc, "encounter_id"),
                recorded_at=reading.recorded_at or _now(),
                recorded_by=_parse_uuid(reading.recorded_by, "recorded_by"),
                vital_type=reading.vital_type,
                value_numeric=value_numeric,
                value_text=value_text,
                unit=unit,
                notion=reading.notion,
            )
            session.add(vital)
            recorded.append(vital)
        await session.flush()
        await self._timeline(
            session,
            patient_id,
            "VITALS_RECORDED",
            entity_type="vital_signs",
            details={"count": len(recorded), "types": [r.vital_type for r in recorded]},
        )
        return recorded

    async def list_vitals(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        vital_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[VitalSign], int]:
        limit, offset = self._limit(self.settings, limit, offset)
        query = select(VitalSign).where(VitalSign.patient_id == patient_id, VitalSign.deleted_at.is_(None))
        count_query = select(func.count(VitalSign.id)).where(
            VitalSign.patient_id == patient_id, VitalSign.deleted_at.is_(None)
        )
        if vital_type:
            query = query.where(VitalSign.vital_type == vital_type.upper())
            count_query = count_query.where(VitalSign.vital_type == vital_type.upper())
        total = await session.scalar(count_query)
        rows = await session.scalars(
            query.order_by(VitalSign.recorded_at.desc()).limit(limit).offset(offset)
        )
        return list(rows), int(total or 0)

    # --------------------------------------------------------------- diagnoses

    async def add_diagnosis(
        self, session: AsyncSession, patient_id: uuid.UUID, payload: dto.DiagnosisIn
    ) -> Diagnosis:
        diagnosis = Diagnosis(
            patient_id=patient_id,
            encounter_id=_parse_uuid(payload.encounter_id, "encounter_id"),
            diagnosis_code=payload.diagnosis_code,
            code_system=payload.code_system,
            description=payload.description,
            type=payload.type,
            onset_date=payload.onset_date,
            diagnosed_by=_parse_uuid(payload.diagnosed_by, "diagnosed_by"),
            present_on_admission=payload.present_on_admission,
            status="ACTIVE",
        )
        session.add(diagnosis)
        await session.flush()
        await self._timeline(
            session,
            patient_id,
            "DIAGNOSIS_ADDED",
            entity_type="diagnosis",
            entity_id=diagnosis.id,
            actor_id=diagnosis.diagnosed_by,
            details={"code": payload.diagnosis_code, "type": payload.type},
        )
        return diagnosis

    async def list_diagnoses(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[Diagnosis], int]:
        limit, offset = self._limit(self.settings, limit, offset)
        query = select(Diagnosis).where(Diagnosis.patient_id == patient_id, Diagnosis.deleted_at.is_(None))
        count_query = select(func.count(Diagnosis.id)).where(
            Diagnosis.patient_id == patient_id, Diagnosis.deleted_at.is_(None)
        )
        if status:
            query = query.where(Diagnosis.status == status.upper())
            count_query = count_query.where(Diagnosis.status == status.upper())
        total = await session.scalar(count_query)
        rows = await session.scalars(
            query.order_by(Diagnosis.diagnosed_at.desc()).limit(limit).offset(offset)
        )
        return list(rows), int(total or 0)

    async def resolve_diagnosis(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        diagnosis_id: uuid.UUID,
        payload: dto.DiagnosisResolveIn,
    ) -> Diagnosis:
        diagnosis = await self._get_owned(session, Diagnosis, patient_id, diagnosis_id)
        if diagnosis.status == "RESOLVED":
            raise EhrError("DIAGNOSIS_RESOLVED", "diagnosis is already resolved", 409)
        diagnosis.status = "RESOLVED"
        diagnosis.resolved_at = payload.resolved_at or _now()
        diagnosis.resolved_by = _parse_uuid(payload.resolved_by, "resolved_by")
        await self._timeline(
            session,
            patient_id,
            "DIAGNOSIS_RESOLVED",
            entity_type="diagnosis",
            entity_id=diagnosis.id,
            actor_id=diagnosis.resolved_by,
        )
        return diagnosis

    # -------------------------------------------------------------- medications

    async def add_medication(
        self, session: AsyncSession, patient_id: uuid.UUID, payload: dto.MedicationIn
    ) -> Medication:
        medication = Medication(
            patient_id=patient_id,
            encounter_id=_parse_uuid(payload.encounter_id, "encounter_id"),
            medication_id=_parse_uuid(payload.medication_id, "medication_id"),
            medication_name=payload.medication_name,
            strength=payload.strength,
            dose=payload.dose,
            dose_unit=payload.dose_unit,
            route=payload.route,
            frequency=payload.frequency,
            duration=payload.duration,
            prn=payload.prn,
            start_date=payload.start_date,
            end_date=payload.end_date,
            indication=payload.indication,
            instructions=payload.instructions,
            prescriber_id=_parse_uuid(payload.prescriber_id, "prescriber_id"),
            prescribed_at=_now(),
            status="ACTIVE",
        )
        session.add(medication)
        await session.flush()
        await self._timeline(
            session,
            patient_id,
            "MEDICATION_ORDERED",
            entity_type="medication",
            entity_id=medication.id,
            actor_id=medication.prescriber_id,
            details={"medication_name": payload.medication_name, "route": payload.route},
        )
        return medication

    async def list_medications(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[Medication], int]:
        limit, offset = self._limit(self.settings, limit, offset)
        query = select(Medication).where(Medication.patient_id == patient_id, Medication.deleted_at.is_(None))
        count_query = select(func.count(Medication.id)).where(
            Medication.patient_id == patient_id, Medication.deleted_at.is_(None)
        )
        if status:
            query = query.where(Medication.status == status.upper())
            count_query = count_query.where(Medication.status == status.upper())
        total = await session.scalar(count_query)
        rows = await session.scalars(
            query.order_by(Medication.prescribed_at.desc()).limit(limit).offset(offset)
        )
        return list(rows), int(total or 0)

    async def update_medication(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        medication_id: uuid.UUID,
        payload: dto.MedicationUpdateIn,
    ) -> Medication:
        medication = await self._get_owned(session, Medication, patient_id, medication_id)
        if payload.status == "DISCONTINUED" or payload.distribution_forbid:
            if payload.status == "DISCONTINUED":
                medication.status = "DISCONTINUED"
                medication.discontinued_at = _now()
                medication.discontinued_by = _parse_uuid(payload.discontinued_by, "discontinued_by")
                await self._timeline(
                    session,
                    patient_id,
                    "MEDICATION_DISCONTINUED",
                    entity_type="medication",
                    entity_id=medication.id,
                    actor_id=medication.discontinued_by,
                    details={"medication_name": medication.medication_name},
                )
        elif payload.status:
            medication.status = payload.status
        if payload.instructions is not None:
            medication.instructions = payload.instructions
        return medication

    # --------------------------------------------------------------- orders

    async def add_order(
        self, session: AsyncSession, patient_id: uuid.UUID, payload: dto.ClinicalOrderIn
    ) -> ClinicalOrder:
        order = ClinicalOrder(
            patient_id=patient_id,
            encounter_id=_parse_uuid(payload.encounter_id, "encounter_id"),
            order_type=payload.order_type,
            description=payload.description,
            priority=payload.priority,
            indications=payload.indications,
            requested_by=_parse_uuid(payload.requested_by, "requested_by"),
            requested_at=_now(),
            external_ref=_parse_uuid(payload.external_ref, "external_ref"),
            status="REQUESTED",
        )
        session.add(order)
        await session.flush()
        await self._timeline(
            session,
            patient_id,
            "ORDER_REQUESTED",
            entity_type="clinical_order",
            entity_id=order.id,
            actor_id=order.requested_by,
            details={"order_type": payload.order_type, "priority": payload.priority},
        )
        return order

    async def list_orders(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        order_type: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[ClinicalOrder], int]:
        limit, offset = self._limit(self.settings, limit, offset)
        query = select(ClinicalOrder).where(ClinicalOrder.patient_id == patient_id, ClinicalOrder.deleted_at.is_(None))
        count_query = select(func.count(ClinicalOrder.id)).where(
            ClinicalOrder.patient_id == patient_id, ClinicalOrder.deleted_at.is_(None)
        )
        if order_type:
            query = query.where(ClinicalOrder.order_type == order_type.upper())
            count_query = count_query.where(ClinicalOrder.order_type == order_type.upper())
        if status:
            query = query.where(ClinicalOrder.status == status.upper())
            count_query = count_query.where(ClinicalOrder.status == status.upper())
        total = await session.scalar(count_query)
        rows = await session.scalars(
            query.order_by(ClinicalOrder.requested_at.desc()).limit(limit).offset(offset)
        )
        return list(rows), int(total or 0)

    async def update_order(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        order_id: uuid.UUID,
        payload: dto.ClinicalOrderUpdateIn,
    ) -> ClinicalOrder:
        order = await self._get_owned(session, ClinicalOrder, patient_id, order_id)
        timeline_event: str | None = None
        if payload.status:
            order.status = payload.status
            if payload.status == "COMPLETED":
                order.completed_at = _now()
                order.completed_by = _parse_uuid(payload.completed_by, "completed_by")
                timeline_event = "ORDER_COMPLETED"
            elif payload.status == "CANCELLED":
                timeline_event = "ORDER_CANCELLED"
        if payload.result_summary is not None:
            order.result_summary = payload.result_summary
        if order.status == "COMPLETED" and not order.result_summary:
            order.result_summary = "completed"
        if timeline_event:
            await self._timeline(
                session,
                patient_id,
                timeline_event,
                entity_type="clinical_order",
                entity_id=order.id,
                actor_id=(
                    _parse_uuid(payload.completed_by, "completed_by") if payload.completed_by else order.requested_by
                ),
                details={"status": order.status},
            )
        return order

    # --------------------------------------------------------------- allergies

    async def add_allergy(
        self, session: AsyncSession, patient_id: uuid.UUID, payload: dto.AllergyIn
    ) -> PatientAllergy:
        allergy = PatientAllergy(
            patient_id=patient_id,
            encounter_id=_parse_uuid(payload.encounter_id, "encounter_id"),
            allergen=payload.allergen,
            allergen_type=payload.allergen_type,
            reaction=payload.reaction,
            severity=payload.severity,
            onset_date=payload.onset_date,
            recorded_by=_parse_uuid(payload.recorded_by, "recorded_by"),
            recorded_at=_now(),
            status="ACTIVE",
        )
        session.add(allergy)
        try:
            await session.flush()
        except Exception as err:  # noqa: BLE001 - unique violation from (patient, allergen, type)
            await session.rollback()
            raise EhrError(
                "ALLERGY_EXISTS", f"allergy '{payload.allergen}' already recorded for this patient", 409
            ) from err
        await self._timeline(
            session,
            patient_id,
            "ALLERGY_ADDED",
            entity_type="patient_allergy",
            entity_id=allergy.id,
            actor_id=allergy.recorded_by,
            details={"allergen": payload.allergen, "severity": payload.severity},
        )
        return allergy

    async def list_allergies(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[PatientAllergy], int]:
        limit, offset = self._limit(self.settings, limit, offset)
        query = select(PatientAllergy).where(
            PatientAllergy.patient_id == patient_id, PatientAllergy.deleted_at.is_(None)
        )
        count_query = select(func.count(PatientAllergy.id)).where(
            PatientAllergy.patient_id == patient_id, PatientAllergy.deleted_at.is_(None)
        )
        if status:
            query = query.where(PatientAllergy.status == status.upper())
            count_query = count_query.where(PatientAllergy.status == status.upper())
        total = await session.scalar(count_query)
        rows = await session.scalars(query.order_by(PatientAllergy.recorded_at.desc()).limit(limit).offset(offset))
        return list(rows), int(total or 0)

    async def resolve_allergy(
        self, session: AsyncSession, patient_id: uuid.UUID, allergy_id: uuid.UUID
    ) -> PatientAllergy:
        allergy = await self._get_owned(session, PatientAllergy, patient_id, allergy_id)
        if allergy.status == "RESOLVED":
            raise EhrError("ALLERGY_RESOLVED", "allergy is already resolved", 409)
        allergy.status = "RESOLVED"
        allergy.resolved_at = _now()
        await self._timeline(
            session,
            patient_id,
            "ALLERGY_RESOLVED",
            entity_type="patient_allergy",
            entity_id=allergy.id,
        )
        return allergy

    # -------------------------------------------------------- problem list

    async def add_problem(
        self, session: AsyncSession, patient_id: uuid.UUID, payload: dto.ProblemIn
    ) -> ProblemListEntry:
        problem = ProblemListEntry(
            patient_id=patient_id,
            problem=payload.problem,
            diagnosis_code=payload.diagnosis_code,
            code_system=payload.code_system,
            onset_date=payload.onset_date,
            severity=payload.severity,
            note=payload.note,
            recorded_by=_parse_uuid(payload.recorded_by, "recorded_by"),
            status="ACTIVE",
        )
        session.add(problem)
        await session.flush()
        await self._timeline(
            session,
            patient_id,
            "PROBLEM_ADDED",
            entity_type="problem_list",
            entity_id=problem.id,
            actor_id=problem.recorded_by,
            details={"problem": payload.problem},
        )
        return problem

    async def list_problems(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[ProblemListEntry], int]:
        limit, offset = self._limit(self.settings, limit, offset)
        query = select(ProblemListEntry).where(
            ProblemListEntry.patient_id == patient_id, ProblemListEntry.deleted_at.is_(None)
        )
        count_query = select(func.count(ProblemListEntry.id)).where(
            ProblemListEntry.patient_id == patient_id, ProblemListEntry.deleted_at.is_(None)
        )
        if status:
            query = query.where(ProblemListEntry.status == status.upper())
            count_query = count_query.where(ProblemListEntry.status == status.upper())
        total = await session.scalar(count_query)
        rows = await session.scalars(query.order_by(ProblemListEntry.created_at.desc()).limit(limit).offset(offset))
        return list(rows), int(total or 0)

    async def resolve_problem(
        self, session: AsyncSession, patient_id: uuid.UUID, problem_id: uuid.UUID
    ) -> ProblemListEntry:
        problem = await self._get_owned(session, ProblemListEntry, patient_id, problem_id)
        if problem.status == "RESOLVED":
            raise EhrError("PROBLEM_RESOLVED", "problem is already resolved", 409)
        problem.status = "RESOLVED"
        problem.resolved_date = date.today()
        await self._timeline(
            session,
            patient_id,
            "PROBLEM_RESOLVED",
            entity_type="problem_list",
            entity_id=problem.id,
        )
        return problem

    # ---------------------------------------------------------- medical history

    async def add_medical_history(
        self, session: AsyncSession, patient_id: uuid.UUID, payload: dto.MedicalHistoryIn
    ) -> MedicalHistory:
        entry = MedicalHistory(
            patient_id=patient_id,
            encounter_id=_parse_uuid(payload.encounter_id, "encounter_id"),
            history_type=payload.history_type,
            description=payload.description,
            occurred_date=payload.occurred_date,
            resolved_date=payload.resolved_date,
            facility=payload.facility,
            notes=payload.notes,
            recorded_by=_parse_uuid(payload.recorded_by, "recorded_by"),
            status="ACTIVE",
        )
        session.add(entry)
        await session.flush()
        await self._timeline(
            session,
            patient_id,
            "HISTORY_RECORDED",
            entity_type="medical_history",
            entity_id=entry.id,
            actor_id=entry.recorded_by,
            details={"history_type": payload.history_type},
        )
        return entry

    async def list_medical_history(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        history_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[MedicalHistory], int]:
        limit, offset = self._limit(self.settings, limit, offset)
        query = select(MedicalHistory).where(
            MedicalHistory.patient_id == patient_id, MedicalHistory.deleted_at.is_(None)
        )
        count_query = select(func.count(MedicalHistory.id)).where(
            MedicalHistory.patient_id == patient_id, MedicalHistory.deleted_at.is_(None)
        )
        if history_type:
            query = query.where(MedicalHistory.history_type == history_type.upper())
            count_query = count_query.where(MedicalHistory.history_type == history_type.upper())
        total = await session.scalar(count_query)
        rows = await session.scalars(query.order_by(MedicalHistory.created_at.desc()).limit(limit).offset(offset))
        return list(rows), int(total or 0)

    # ---------------------------------------------------------------- timeline

    async def get_timeline(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[ClinicalTimelineEvent], int]:
        limit, offset = 1000 if limit is None else limit, offset or 0
        limit = max(1, min(limit, self.settings.max_timeline_entries))
        total = await session.scalar(
            select(func.count(ClinicalTimelineEvent.id)).where(ClinicalTimelineEvent.patient_id == patient_id)
        )
        rows = await session.scalars(
            select(ClinicalTimelineEvent)
            .where(ClinicalTimelineEvent.patient_id == patient_id)
            .order_by(ClinicalTimelineEvent.occurred_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total or 0)

    # ------------------------------------------------------------------- chart

    async def get_chart(self, session: AsyncSession, patient_id: uuid.UUID) -> dict:
        """Aggregate the full clinical record for a patient."""
        sections: dict[str, dict] = {}

        async def _section(name: str, scalar_select, row_mapper) -> None:
            rows = await session.scalars(scalar_select)
            items = [row_mapper(row) for row in rows]
            sections[name] = {"count": len(items), "items": items}

        await _section("encounters", _patient_select(Encounter, patient_id, "start_time"), encounter_out)
        await _section("notes", _patient_select(ClinicalNote, patient_id, "created_at"), note_out)
        await _section("vitals", _patient_select(VitalSign, patient_id, "recorded_at"), vital_out)
        await _section("diagnoses", _patient_select(Diagnosis, patient_id, "diagnosed_at"), diagnosis_out)
        await _section("medications", _patient_select(Medication, patient_id, "prescribed_at"), medication_out)
        await _section("orders", _patient_select(ClinicalOrder, patient_id, "requested_at"), order_out)
        await _section("allergies", _patient_select(PatientAllergy, patient_id, "recorded_at"), allergy_out)
        await _section("problems", _patient_select(ProblemListEntry, patient_id, "created_at"), problem_out)
        await _section(
            "medical_history", _patient_select(MedicalHistory, patient_id, "created_at"), medical_history_out
        )
        await _section("treatments", _patient_select(Treatment, patient_id, "created_at"), treatment_out)
        await _section("care_plans", _patient_select(CarePlan, patient_id, "created_at"), care_plan_out)
        await _section("referrals", _patient_select(Referral, patient_id, "created_at"), referral_out)
        return {"patient_id": str(patient_id), "sections": sections}

    # ------------------------------------------------------------- shared fetch

    async def _get_owned(self, session, model, patient_id: uuid.UUID, row_id: uuid.UUID):
        row = await session.get(model, row_id)
        if row is None or row.deleted_at is not None or row.patient_id != patient_id:
            raise EhrError("NOT_FOUND", f"{_name(model.__name__)} not found for this patient", 404)
        return row


# --- serializers -------------------------------------------------------------

def _dt(value: datetime | None) -> str | None:
    value = _as_aware(value)
    return value.isoformat() if value else None


def _d(value: date | None) -> str | None:
    return value.isoformat() if value else None


def encounter_out(e: Encounter) -> dict:
    return {
        "id": str(e.id),
        "patient_id": str(e.patient_id),
        "encounter_type": e.encounter_type,
        "visit_number": e.visit_number,
        "department_id": str(e.department_id) if e.department_id else None,
        "provider_id": str(e.provider_id) if e.provider_id else None,
        "start_time": _dt(e.start_time),
        "end_time": _dt(e.end_time),
        "reason": e.reason,
        "status": e.status,
        "created_at": _dt(e.created_at),
    }


def note_out(n: ClinicalNote) -> dict:
    return {
        "id": str(n.id),
        "patient_id": str(n.patient_id),
        "encounter_id": str(n.encounter_id) if n.encounter_id else None,
        "note_type": n.note_type,
        "content": n.content,
        "content_struct": n.content_struct,
        "author_id": str(n.author_id) if n.author_id else None,
        "author_role": n.author_role,
        "approval_status": n.approval_status,
        "source": n.source,
        "created_at": _dt(n.created_at),
        "updated_at": _dt(n.updated_at),
    }


def version_out(v: ClinicalNoteVersion) -> dict:
    return {
        "id": str(v.id),
        "note_id": str(v.note_id),
        "version_no": v.version_no,
        "content": v.content,
        "content_struct": v.content_struct,
        "author_id": str(v.author_id) if v.author_id else None,
        "change_reason": v.change_reason,
        "created_at": _dt(v.created_at),
    }


def amendment_out(a: ClinicalNoteAmendment) -> dict:
    return {
        "id": str(a.id),
        "note_id": str(a.note_id),
        "author_id": str(a.author_id) if a.author_id else None,
        "amendment": a.amendment,
        "added_at": _dt(a.added_at),
    }


def vital_out(v: VitalSign) -> dict:
    return {
        "id": str(v.id),
        "patient_id": str(v.patient_id),
        "encounter_id": str(v.encounter_id) if v.encounter_id else None,
        "vital_type": v.vital_type,
        "value_numeric": float(v.value_numeric) if v.value_numeric is not None else None,
        "value_text": v.value_text,
        "unit": v.unit,
        "recorded_at": _dt(v.recorded_at),
        "recorded_by": str(v.recorded_by) if v.recorded_by else None,
    }


def diagnosis_out(d: Diagnosis) -> dict:
    return {
        "id": str(d.id),
        "patient_id": str(d.patient_id),
        "encounter_id": str(d.encounter_id) if d.encounter_id else None,
        "diagnosis_code": d.diagnosis_code,
        "code_system": d.code_system,
        "description": d.description,
        "type": d.type,
        "onset_date": _d(d.onset_date),
        "diagnosed_by": str(d.diagnosed_by) if d.diagnosed_by else None,
        "diagnosed_at": _dt(d.diagnosed_at),
        "resolved_at": _dt(d.resolved_at),
        "status": d.status,
    }


def medication_out(m: Medication) -> dict:
    return {
        "id": str(m.id),
        "patient_id": str(m.patient_id),
        "encounter_id": str(m.encounter_id) if m.encounter_id else None,
        "medication_name": m.medication_name,
        "strength": m.strength,
        "dose": float(m.dose) if m.dose is not None else None,
        "dose_unit": m.dose_unit,
        "route": m.route,
        "frequency": m.frequency,
        "prn": m.prn,
        "start_date": _d(m.start_date),
        "end_date": _d(m.end_date),
        "indication": m.indication,
        "instructions": m.instructions,
        "prescriber_id": str(m.prescriber_id) if m.prescriber_id else None,
        "prescribed_at": _dt(m.prescribed_at),
        "discontinued_at": _dt(m.discontinued_at),
        "status": m.status,
    }


def order_out(o: ClinicalOrder) -> dict:
    return {
        "id": str(o.id),
        "patient_id": str(o.patient_id),
        "encounter_id": str(o.encounter_id) if o.encounter_id else None,
        "order_type": o.order_type,
        "description": o.description,
        "priority": o.priority,
        "indications": o.indications,
        "requested_by": str(o.requested_by) if o.requested_by else None,
        "requested_at": _dt(o.requested_at),
        "result_summary": o.result_summary,
        "completed_at": _dt(o.completed_at),
        "status": o.status,
    }


def allergy_out(a: PatientAllergy) -> dict:
    return {
        "id": str(a.id),
        "patient_id": str(a.patient_id),
        "encounter_id": str(a.encounter_id) if a.encounter_id else None,
        "allergen": a.allergen,
        "allergen_type": a.allergen_type,
        "reaction": a.reaction,
        "severity": a.severity,
        "onset_date": _d(a.onset_date),
        "recorded_at": _dt(a.recorded_at),
        "resolved_at": _dt(a.resolved_at),
        "status": a.status,
    }


def problem_out(p: ProblemListEntry) -> dict:
    return {
        "id": str(p.id),
        "patient_id": str(p.patient_id),
        "problem": p.problem,
        "diagnosis_code": p.diagnosis_code,
        "code_system": p.code_system,
        "onset_date": _d(p.onset_date),
        "resolved_date": _d(p.resolved_date),
        "severity": p.severity,
        "note": p.note,
        "recorded_by": str(p.recorded_by) if p.recorded_by else None,
        "status": p.status,
    }


def medical_history_out(h: MedicalHistory) -> dict:
    return {
        "id": str(h.id),
        "patient_id": str(h.patient_id),
        "encounter_id": str(h.encounter_id) if h.encounter_id else None,
        "history_type": h.history_type,
        "description": h.description,
        "occurred_date": _d(h.occurred_date),
        "resolved_date": _d(h.resolved_date),
        "facility": h.facility,
        "notes": h.notes,
        "recorded_by": str(h.recorded_by) if h.recorded_by else None,
        "created_at": _dt(h.created_at),
        "status": h.status,
    }


def treatment_out(t: Treatment) -> dict:
    return {
        "id": str(t.id),
        "patient_id": str(t.patient_id),
        "encounter_id": str(t.encounter_id) if t.encounter_id else None,
        "treatment_type": t.treatment_type,
        "description": t.description,
        "performed_at": _dt(t.performed_at),
        "outcome": t.outcome,
        "status": t.status,
    }


def care_plan_out(c: CarePlan) -> dict:
    return {
        "id": str(c.id),
        "patient_id": str(c.patient_id),
        "title": c.title,
        "goal": c.goal,
        "start_date": _d(c.start_date),
        "end_date": _d(c.end_date),
        "status": c.status,
    }


def referral_out(r: Referral) -> dict:
    return {
        "id": str(r.id),
        "patient_id": str(r.patient_id),
        "referral_type": r.referral_type,
        "reason": r.reason,
        "status": r.status,
    }


def timeline_out(t: ClinicalTimelineEvent) -> dict:
    return {
        "id": str(t.id),
        "patient_id": str(t.patient_id),
        "event_type": t.event_type,
        "source": t.source,
        "entity_type": t.entity_type,
        "entity_id": str(t.entity_id) if t.entity_id else None,
        "occurred_at": _dt(t.occurred_at),
        "actor_id": str(t.actor_id) if t.actor_id else None,
        "details": t.details,
    }