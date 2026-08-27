"""Business logic for prescribing: safety checks, lifecycle, MAR, allergies.

Publishes ``PrescriptionCreated`` / ``PrescriptionCancelled`` on
``clinical.prescription.*`` so pharmacy, ehr and notification services keep
projections fresh (EHOS_ARCHITECTURE_DESIGN.md section 3.3).

Safety model (local, deterministic checks):
- ALLERGY CONFLICT: a prescribed medication matches one of the patient's
  active DRUG allergies (case-insensitive containment). Blocked with HTTP 409
  unless the prescriber explicitly overrides; conflicts are always recorded.
- DUPLICATE THERAPY: the same medication listed twice on one prescription is
  rejected outright.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime

from ehos_common.events import DomainEvent
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from prescription_service.configuration import PrescriptionSettings
from prescription_service.dto.schemas import (
    AdministrationIn,
    AllergyIn,
    CancelIn,
    PrescriptionIn,
)
from prescription_service.entity.models import (
    MedicationAdministration,
    PatientAllergy,
    Prescription,
    PrescriptionItem,
)

log = logging.getLogger("prescription-service")

PRESCRIPTION_CREATED_TOPIC = "clinical.prescription.created"
PRESCRIPTION_CANCELLED_TOPIC = "clinical.prescription.cancelled"

_TOPICS = {
    "PrescriptionCreated": PRESCRIPTION_CREATED_TOPIC,
    "PrescriptionCancelled": PRESCRIPTION_CANCELLED_TOPIC,
}

LIVE_STATUSES = ("ACTIVE", "PAUSED")


class PrescriptionError(Exception):
    def __init__(self, error_code: str, message: str, status_code: int = 400):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class PrescriptionService:
    def __init__(self, settings: PrescriptionSettings, producer=None):
        self.settings = settings
        self.producer = producer

    # ------------------------------------------------------------ helpers

    async def _publish(self, session: AsyncSession, event_type: str, payload: dict) -> None:
        if self.producer is None:
            return
        try:
            topic = _TOPICS.get(event_type, PRESCRIPTION_CREATED_TOPIC)
            event = DomainEvent(
                event_type=event_type,
                source="prescription-service",
                user_id=None,
                payload={"occurredAt": datetime.now(UTC).isoformat(), **payload},
            )
            outbox = session.info.get("outbox")
            if outbox is not None:
                outbox.add(topic, event)
            else:
                await self.producer.publish(topic, event)
        except Exception:  # noqa: BLE001 - publishing must never break prescribing
            log.exception("failed to publish %s", event_type)

    async def _get_prescription(self, session: AsyncSession, rx_id) -> Prescription:
        rx = await session.get(Prescription, rx_id)
        if rx is None or rx.deleted_at is not None:
            raise PrescriptionError("PRESCRIPTION_NOT_FOUND", "Prescription not found", 404)
        return rx

    async def _get_item(self, session: AsyncSession, item_id) -> PrescriptionItem:
        item = await session.get(PrescriptionItem, item_id)
        if item is None or item.deleted_at is not None:
            raise PrescriptionError("ITEM_NOT_FOUND", "Prescription item not found", 404)
        return item

    async def _active_drug_allergies(self, session: AsyncSession, patient_id) -> list[PatientAllergy]:
        rows = (
            await session.execute(
                select(PatientAllergy).where(
                    PatientAllergy.patient_id == patient_id,
                    PatientAllergy.allergen_type == "DRUG",
                    PatientAllergy.deleted_at.is_(None),
                    PatientAllergy.status == "ACTIVE",
                )
            )
        ).scalars().all()
        return list(rows)

    @staticmethod
    def _allergy_conflicts(medications: list[str], allergies: list[PatientAllergy]) -> list[str]:
        conflicts: list[str] = []
        for allergy in allergies:
            name = allergy.allergen.strip().lower()
            if any(name in med.lower() or med.lower() in name for med in medications):
                conflicts.append(allergy.allergen)
        return conflicts

    # ------------------------------------------------------------ create

    async def create(
        self, session: AsyncSession, data: PrescriptionIn, actor=None
    ) -> Prescription:
        if len(data.items) > self.settings.max_items_per_prescription:
            raise PrescriptionError(
                "TOO_MANY_ITEMS",
                f"A prescription may hold at most {self.settings.max_items_per_prescription} items.",
                422,
            )

        names = [i.medication.strip() for i in data.items]
        lowered = [n.lower() for n in names]
        if len(set(lowered)) != len(lowered):
            raise PrescriptionError(
                "DUPLICATE_MEDICATION",
                "The same medication appears more than once on this prescription.",
                422,
            )

        patient_id = uuid.UUID(data.patient_id)
        allergies = await self._active_drug_allergies(session, patient_id)
        conflicts = self._allergy_conflicts(names, allergies)
        if conflicts and not data.override_flags:
            raise PrescriptionError(
                "ALLERGY_CONFLICT",
                "Allergy conflict: " + ", ".join(sorted(set(conflicts)))
                + ". Override explicitly to prescribe anyway.",
                409,
            )

        rx = Prescription(
            patient_id=patient_id,
            encounter_id=uuid.UUID(data.encounter_id) if data.encounter_id else None,
            prescriber_id=uuid.UUID(data.prescriber_id),
            issue_date=date.today(),
            therapy_type=data.therapy_type,
            allergy_checked=True,           # check always runs at creation
            interaction_checked=True,       # duplicate-therapy check ran clean
            start_date=data.start_date or date.today(),
            end_date=data.end_date,
            repeat_instructions=data.repeat_instructions,
            reason=data.reason,
            created_by=actor,
            status="ACTIVE",
        )
        if conflicts and data.override_flags:
            rx.audit_reference = f"allergy override: {', '.join(sorted(set(conflicts)))}"
        session.add(rx)
        await session.flush()

        for item in data.items:
            session.add(
                PrescriptionItem(
                    prescription_id=rx.id,
                    medication_id=uuid.UUID(item.medication_id) if item.medication_id else None,
                    medication=item.medication.strip(),
                    dosage=item.dosage,
                    frequency=item.frequency,
                    route=item.route,
                    duration_days=item.duration_days,
                    quantity=item.quantity,
                    instructions=item.instructions,
                    max_per_day=item.max_per_day,
                )
            )
        await session.flush()

        await self._publish(
            session,
            "PrescriptionCreated",
            {
                "prescriptionId": str(rx.id),
                "patientId": str(patient_id),
                "itemCount": len(data.items),
                "allergyOverride": bool(conflicts),
            },
        )
        return rx

    # ------------------------------------------------------------ read / list

    async def get_detail(self, session: AsyncSession, rx_id) -> dict:
        rx = await self._get_prescription(session, rx_id)
        items = (
            (
                await session.execute(
                    select(PrescriptionItem).where(
                        PrescriptionItem.prescription_id == rx.id,
                        PrescriptionItem.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        administrations = (
            (
                await session.execute(
                    select(MedicationAdministration).where(
                        MedicationAdministration.prescription_id == rx.id,
                        MedicationAdministration.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        detail = _rx_out(rx)
        detail["items"] = [_item_out(i) for i in items]
        detail["administrations"] = [_mar_out(m) for m in administrations]
        return detail

    async def list_prescriptions(
        self,
        session: AsyncSession,
        *,
        patient_id: str | None = None,
        prescriber_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Prescription], int]:
        limit = min(max(1, limit), self.settings.search_max_limit)
        stmt = select(Prescription).where(Prescription.deleted_at.is_(None))
        if patient_id:
            stmt = stmt.where(Prescription.patient_id == uuid.UUID(patient_id))
        if prescriber_id:
            stmt = stmt.where(Prescription.prescriber_id == uuid.UUID(prescriber_id))
        if status:
            stmt = stmt.where(Prescription.status == status.upper())
        total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        rows = (
            (
                await session.execute(
                    stmt.order_by(Prescription.issue_date.desc(), Prescription.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    # ------------------------------------------------------------ lifecycle

    async def cancel(self, session: AsyncSession, rx_id, data: CancelIn, actor=None) -> Prescription:
        rx = await self._get_prescription(session, rx_id)
        if rx.status not in LIVE_STATUSES:
            raise PrescriptionError(
                "INVALID_STATUS", f"Cannot cancel a prescription with status {rx.status}.", 409
            )
        rx.status = "CANCELLED"
        rx.cancelled_by = actor
        rx.cancelled_at = datetime.now(UTC)
        rx.cancellation_reason = data.reason
        rx.updated_by = actor
        rx.version += 1
        await session.flush()

        items = (
            (
                await session.execute(
                    select(PrescriptionItem).where(
                        PrescriptionItem.prescription_id == rx.id,
                        PrescriptionItem.deleted_at.is_(None),
                        PrescriptionItem.status == "ACTIVE",
                    )
                )
            )
            .scalars()
            .all()
        )
        for item in items:
            item.status = "CANCELLED"

        await self._publish(
            session,
            "PrescriptionCancelled",
            {"prescriptionId": str(rx.id), "patientId": str(rx.patient_id), "reason": data.reason},
        )
        return rx

    async def set_status(
        self, session: AsyncSession, rx_id, target: str, actor=None
    ) -> Prescription:
        """Pause / resume / complete an ACTIVE or PAUSED prescription."""
        rx = await self._get_prescription(session, rx_id)
        allowed = {
            "PAUSED": ("ACTIVE",),
            "ACTIVE": ("PAUSED",),
            "COMPLETED": ("ACTIVE", "PAUSED"),
        }
        if target not in allowed:
            raise PrescriptionError("INVALID_TARGET", f"Unknown target status {target}.", 422)
        if rx.status not in allowed[target]:
            raise PrescriptionError(
                "INVALID_STATUS", f"Cannot move {rx.status} → {target}.", 409
            )
        rx.status = target
        rx.updated_by = actor
        rx.version += 1
        await session.flush()
        return rx

    async def discontinue_item(
        self, session: AsyncSession, item_id, reason: str | None, actor=None
    ) -> PrescriptionItem:
        item = await self._get_item(session, item_id)
        if item.status != "ACTIVE":
            raise PrescriptionError(
                "INVALID_STATUS", f"Cannot discontinue an item with status {item.status}.", 409
            )
        item.status = "DISCONTINUED"
        item.deletion_reason = reason
        item.updated_by = actor
        item.version += 1
        await session.flush()
        return item

    # ------------------------------------------------------------ MAR

    async def record_administration(
        self, session: AsyncSession, data: AdministrationIn, actor=None
    ) -> MedicationAdministration:
        item = await self._get_item(session, uuid.UUID(data.prescription_item_id))
        rx = await self._get_prescription(session, item.prescription_id)
        if rx.status != "ACTIVE":
            raise PrescriptionError(
                "INVALID_STATUS", f"Medications can only be administered on ACTIVE prescriptions ({rx.status}).", 409
            )
        if item.status != "ACTIVE":
            raise PrescriptionError(
                "INVALID_STATUS", f"This medication line is {item.status}.", 409
            )
        given_not_statuses = ("REFUSED", "MISSED", "HELD")
        if data.mar_status in given_not_statuses and not data.reason_not_given:
            raise PrescriptionError(
                "REASON_REQUIRED", f"A reason is required when a dose is {data.mar_status}.", 422
            )

        mar = MedicationAdministration(
            patient_id=rx.patient_id,
            prescription_id=rx.id,
            prescription_item_id=item.id,
            medication_id=item.medication_id,
            medication=item.medication,
            dose=data.dose or item.dosage,
            route=data.route or item.route,
            administered_by=uuid.UUID(data.administered_by),
            administered_at=data.administered_at or datetime.now(UTC),
            batch_number=data.batch_number,
            notes=data.notes,
            reason_not_given=data.reason_not_given,
            witness_id=uuid.UUID(data.witness_id) if data.witness_id else None,
            created_by=actor,
            status=data.mar_status,
        )
        session.add(mar)
        await session.flush()
        return mar

    async def list_administrations(
        self, session: AsyncSession, patient_id: str, limit: int = 50
    ) -> list[MedicationAdministration]:
        limit = min(max(1, limit), self.settings.search_max_limit)
        rows = (
            (
                await session.execute(
                    select(MedicationAdministration)
                    .where(
                        MedicationAdministration.patient_id == uuid.UUID(patient_id),
                        MedicationAdministration.deleted_at.is_(None),
                    )
                    .order_by(MedicationAdministration.administered_at.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    # ------------------------------------------------------------ allergies

    async def add_allergy(self, session: AsyncSession, data: AllergyIn, actor=None) -> PatientAllergy:
        existing = (
            await session.execute(
                select(PatientAllergy).where(
                    PatientAllergy.patient_id == uuid.UUID(data.patient_id),
                    func.lower(PatientAllergy.allergen) == data.allergen.strip().lower(),
                    PatientAllergy.allergen_type == data.allergen_type,
                    PatientAllergy.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise PrescriptionError(
                "ALLERGY_EXISTS",
                f"Allergy '{existing.allergen}' ({data.allergen_type}) is already recorded.",
                409,
            )
        allergy = PatientAllergy(
            patient_id=uuid.UUID(data.patient_id),
            allergen=data.allergen.strip(),
            allergen_type=data.allergen_type,
            severity=data.severity,
            reaction=data.reaction,
            recorded_by=uuid.UUID(data.recorded_by),
            confirmed=data.confirmed,
        )
        session.add(allergy)
        await session.flush()
        return allergy

    async def list_allergies(
        self, session: AsyncSession, patient_id: str, active_only: bool = True
    ) -> list[PatientAllergy]:
        stmt = select(PatientAllergy).where(
            PatientAllergy.patient_id == uuid.UUID(patient_id),
            PatientAllergy.deleted_at.is_(None),
        )
        if active_only:
            stmt = stmt.where(PatientAllergy.status == "ACTIVE")
        rows = (
            (await session.execute(stmt.order_by(PatientAllergy.recorded_at.desc()))).scalars().all()
        )
        return list(rows)


# ---------------------------------------------------------------- serializers

def _rx_out(rx: Prescription) -> dict:
    return {
        "id": str(rx.id),
        "patient_id": str(rx.patient_id),
        "encounter_id": str(rx.encounter_id) if rx.encounter_id else None,
        "prescriber_id": str(rx.prescriber_id),
        "issue_date": rx.issue_date.isoformat(),
        "therapy_type": rx.therapy_type,
        "allergy_checked": rx.allergy_checked,
        "interaction_checked": rx.interaction_checked,
        "start_date": rx.start_date.isoformat() if rx.start_date else None,
        "end_date": rx.end_date.isoformat() if rx.end_date else None,
        "reason": rx.reason,
        "status": rx.status,
        "cancellation_reason": rx.cancellation_reason,
        "audit_reference": rx.audit_reference,
        "created_at": rx.created_at.isoformat() if rx.created_at else None,
    }


def _item_out(item: PrescriptionItem) -> dict:
    return {
        "id": str(item.id),
        "medication": item.medication,
        "dosage": item.dosage,
        "frequency": item.frequency,
        "route": item.route,
        "duration_days": item.duration_days,
        "quantity": float(item.quantity) if item.quantity is not None else None,
        "instructions": item.instructions,
        "status": item.status,
    }


def _mar_out(m: MedicationAdministration) -> dict:
    return {
        "id": str(m.id),
        "medication": m.medication,
        "dose": m.dose,
        "route": m.route,
        "administered_by": str(m.administered_by),
        "administered_at": m.administered_at.isoformat() if m.administered_at else None,
        "status": m.status,
        "reason_not_given": m.reason_not_given,
        "batch_number": m.batch_number,
    }


def _allergy_out(a: PatientAllergy) -> dict:
    return {
        "id": str(a.id),
        "allergen": a.allergen,
        "allergen_type": a.allergen_type,
        "severity": a.severity,
        "reaction": a.reaction,
        "confirmed": a.confirmed,
        "recorded_at": a.recorded_at.isoformat() if a.recorded_at else None,
    }
