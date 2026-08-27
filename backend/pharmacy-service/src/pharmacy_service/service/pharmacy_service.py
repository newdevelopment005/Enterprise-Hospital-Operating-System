"""Business logic for pharmacy: catalog, stock, dispensing, controlled drugs.

Publishes ``MedicationDispensed`` / ``MedicationReturned`` on
``clinical.medication.*`` so billing, ehr and analytics keep projections fresh.

Stock rules:
- FEFO (first-expired-first-out) allocation across batches on dispense.
- Allocation is computed first; insufficient stock raises 409 and mutates
  nothing.
- Controlled drugs require a witness and write an ISSUED/RETURNED entry into
  the immutable controlled-drug log with the running balance.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from ehos_common.events import DomainEvent
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pharmacy_service.configuration import PharmacySettings
from pharmacy_service.dto.schemas import DispenseIn, MedicationIn, StockReceiveIn
from pharmacy_service.entity.models import (
    ControlledDrugLog,
    DispensingRecord,
    Medication,
    StockLevel,
)

log = logging.getLogger("pharmacy-service")

MEDICATION_DISPENSED_TOPIC = "clinical.medication.dispensed"
MEDICATION_RETURNED_TOPIC = "clinical.medication.returned"

_TOPICS = {
    "MedicationDispensed": MEDICATION_DISPENSED_TOPIC,
    "MedicationReturned": MEDICATION_RETURNED_TOPIC,
}


class PharmacyError(Exception):
    def __init__(self, error_code: str, message: str, status_code: int = 400):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class PharmacyService:
    def __init__(self, settings: PharmacySettings, producer=None):
        self.settings = settings
        self.producer = producer

    # ------------------------------------------------------------ helpers

    async def _publish(self, session: AsyncSession, event_type: str, payload: dict) -> None:
        if self.producer is None:
            return
        try:
            topic = _TOPICS.get(event_type, MEDICATION_DISPENSED_TOPIC)
            event = DomainEvent(
                event_type=event_type,
                source="pharmacy-service",
                user_id=None,
                payload={"occurredAt": datetime.now(UTC).isoformat(), **payload},
            )
            outbox = session.info.get("outbox")
            if outbox is not None:
                outbox.add(topic, event)
            else:
                await self.producer.publish(topic, event)
        except Exception:  # noqa: BLE001 - publishing must never break dispensing
            log.exception("failed to publish %s", event_type)

    async def _get_medication(self, session: AsyncSession, med_id) -> Medication:
        med = await session.get(Medication, med_id)
        if med is None or med.deleted_at is not None:
            raise PharmacyError("MEDICATION_NOT_FOUND", "Medication not found", 404)
        return med

    async def _total_stock(self, session: AsyncSession, medication_id) -> Decimal:
        result = await session.execute(
            select(func.coalesce(func.sum(StockLevel.quantity), 0)).where(
                StockLevel.medication_id == medication_id,
                StockLevel.deleted_at.is_(None),
            )
        )
        return Decimal(result.scalar_one())

    async def _available_batches(
        self, session: AsyncSession, medication_id, location: str | None = None
    ) -> list[StockLevel]:
        """Unexpired batches with stock, FEFO order."""
        stmt = select(StockLevel).where(
            StockLevel.medication_id == medication_id,
            StockLevel.deleted_at.is_(None),
            StockLevel.quantity > 0,
        )
        if location:
            stmt = stmt.where(StockLevel.location == location)
        rows = list((await session.execute(stmt)).scalars().all())
        today = date.today()
        rows = [r for r in rows if r.expiry_date is None or r.expiry_date >= today]
        # FEFO: soonest expiry first; batches without expiry last
        rows.sort(key=lambda r: (r.expiry_date is None, r.expiry_date or date.max))
        return rows

    async def _log_controlled(
        self,
        session: AsyncSession,
        medication: Medication,
        batch_number: str,
        action: str,
        quantity: Decimal,
        actor_id,
        witness_id,
        notes: str | None = None,
    ) -> ControlledDrugLog:
        entry = ControlledDrugLog(
            medication_id=medication.id,
            batch_number=batch_number,
            action=action,
            quantity=quantity,
            balance_after=await self._total_stock(session, medication.id),
            actor_id=actor_id,
            witness_id=witness_id,
            notes=notes,
        )
        session.add(entry)
        return entry

    # ------------------------------------------------------------ catalog

    async def create_medication(self, session: AsyncSession, data: MedicationIn, actor=None) -> Medication:
        existing = (
            await session.execute(
                select(Medication).where(Medication.code == data.code, Medication.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise PharmacyError("DUPLICATE_CODE", f"Medication code {data.code} already exists.", 409)
        med = Medication(**data.model_dump(), created_by=actor)
        session.add(med)
        await session.flush()
        return med

    async def search_medications(
        self, session: AsyncSession, q: str | None = None, limit: int = 50, offset: int = 0
    ) -> tuple[list[dict], int]:
        limit = min(max(1, limit), self.settings.search_max_limit)
        stmt = select(Medication).where(Medication.deleted_at.is_(None), Medication.is_active.is_(True))
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(
                Medication.name.ilike(like)
                | Medication.generic_name.ilike(like)
                | Medication.code.ilike(like)
            )
        total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        meds = (
            (await session.execute(stmt.order_by(Medication.name).limit(limit).offset(offset)))
            .scalars()
            .all()
        )

        items: list[dict] = []
        for m in meds:
            total_stock = await self._total_stock(session, m.id)
            items.append({**_med_out(m), "total_stock": float(total_stock)})
        return items, total

    # ------------------------------------------------------------ stock

    async def receive_stock(self, session: AsyncSession, data: StockReceiveIn, actor=None) -> StockLevel:
        med = await self._get_medication(session, uuid.UUID(data.medication_id))

        existing = (
            await session.execute(
                select(StockLevel).where(
                    StockLevel.medication_id == med.id,
                    StockLevel.location == data.location,
                    StockLevel.batch_number == data.batch_number,
                    StockLevel.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

        if existing is not None:
            if existing.expiry_date != data.expiry_date:
                raise PharmacyError(
                    "BATCH_CONFLICT",
                    "Batch already exists with a different expiry date.",
                    409,
                )
            existing.quantity += data.quantity
            row = existing
        else:
            row = StockLevel(
                medication_id=med.id,
                location=data.location,
                batch_number=data.batch_number,
                expiry_date=data.expiry_date,
                quantity=data.quantity,
                created_by=actor,
            )
            session.add(row)

        if med.controlled:
            await self._log_controlled(
                session, med, data.batch_number, "RECEIVED", data.quantity,
                actor_id=actor or uuid.UUID(int=0), witness_id=actor or uuid.UUID(int=0),
                notes="stock receipt",
            )
        await session.flush()
        return row

    async def medication_stock(self, session: AsyncSession, med_id) -> dict:
        med = await self._get_medication(session, med_id)
        batches = (
            (
                await session.execute(
                    select(StockLevel).where(
                        StockLevel.medication_id == med.id,
                        StockLevel.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        return {
            "medication": _med_out(med),
            "total": float(await self._total_stock(session, med.id)),
            "batches": [_stock_out(b) for b in sorted(batches, key=lambda b: b.expiry_date or date.max)],
        }

    async def expiring_soon(self, session: AsyncSession, days: int = 90) -> list[dict]:
        cutoff = date.today() + timedelta(days=min(max(days, 1), 365))
        rows = (
            (
                await session.execute(
                    select(StockLevel).where(
                        StockLevel.deleted_at.is_(None),
                        StockLevel.quantity > 0,
                        StockLevel.expiry_date.is_not(None),
                        StockLevel.expiry_date <= cutoff,
                    ).order_by(StockLevel.expiry_date)
                )
            )
            .scalars()
            .all()
        )
        out: list[dict] = []
        for b in rows:
            med = await session.get(Medication, b.medication_id)
            out.append({**_stock_out(b), "medication_name": med.name if med else "?"})
        return out

    # ------------------------------------------------------------ dispensing

    async def dispense(self, session: AsyncSession, data: DispenseIn, actor=None) -> DispensingRecord:
        med = await self._get_medication(session, uuid.UUID(data.medication_id))
        if med.controlled and not data.witness_id:
            raise PharmacyError(
                "WITNESS_REQUIRED",
                "Controlled drug issue requires a witnessing staff member.",
                422,
            )

        batches = await self._available_batches(session, med.id, data.location)
        available = sum((b.quantity for b in batches), Decimal("0"))
        if available < data.quantity:
            raise PharmacyError(
                "INSUFFICIENT_STOCK",
                f"Only {available} of {med.name} available at {data.location}.",
                409,
            )

        # allocate FEFO, then mutate
        remaining = data.quantity
        used_batches: list[str] = []
        for batch in batches:
            take = min(batch.quantity, remaining)
            batch.quantity -= take
            remaining -= take
            used_batches.append(batch.batch_number or "-")
            if remaining <= 0:
                break

        record = DispensingRecord(
            patient_id=uuid.UUID(data.patient_id),
            prescription_id=uuid.UUID(data.prescription_id) if data.prescription_id else None,
            prescription_item_id=uuid.UUID(data.prescription_item_id) if data.prescription_item_id else None,
            medication_id=med.id,
            quantity=data.quantity,
            dispensed_by=uuid.UUID(data.dispensed_by),
            batch_number=", ".join(used_batches),
            price=data.price,
            notes=data.notes,
            created_by=actor,
            status="DISPENSED",
        )
        session.add(record)
        await session.flush()

        if med.controlled:
            await self._log_controlled(
                session, med, ", ".join(used_batches), "ISSUED", data.quantity,
                actor_id=uuid.UUID(data.dispensed_by),
                witness_id=uuid.UUID(data.witness_id),  # type: ignore[arg-type]
                notes=f"dispensed to patient {data.patient_id}",
            )

        await self._publish(
            session,
            "MedicationDispensed",
            {
                "dispensingId": str(record.id),
                "patientId": data.patient_id,
                "medicationId": str(med.id),
                "quantity": float(data.quantity),
                "prescriptionId": data.prescription_id,
            },
        )
        return record

    async def return_dispensing(self, session: AsyncSession, record_id, reason: str, actor=None) -> DispensingRecord:
        record = await session.get(DispensingRecord, record_id)
        if record is None or record.deleted_at is not None:
            raise PharmacyError("RECORD_NOT_FOUND", "Dispensing record not found", 404)
        if record.status in ("RETURNED",):
            raise PharmacyError("INVALID_STATUS", "This record has already been returned.", 409)

        record.status = "RETURNED"
        record.returned_at = datetime.now(UTC)
        record.returned_reason = reason
        record.updated_by = actor
        record.version += 1

        med = await self._get_medication(session, record.medication_id)

        # restock: split the returned quantity evenly across the issued batches
        batch_names = [b.strip() for b in (record.batch_number or "-").split(",") if b.strip()]
        per_batch = (record.quantity / len(batch_names)).quantize(Decimal("0.01")) if batch_names else Decimal("0")
        for name in batch_names:
            if name == "-":
                continue
            batch = (
                await session.execute(
                    select(StockLevel).where(
                        StockLevel.medication_id == record.medication_id,
                        StockLevel.batch_number == name,
                        StockLevel.deleted_at.is_(None),
                    )
                )
            ).scalars().first()
            if batch is not None:
                batch.quantity += per_batch

        if med.controlled:
            await self._log_controlled(
                session, med, record.batch_number or "-", "RETURNED", record.quantity,
                actor_id=actor or record.dispensed_by,
                witness_id=record.dispensed_by,
                notes=reason,
            )

        await self._publish(
            session,
            "MedicationReturned",
            {"dispensingId": str(record.id), "patientId": str(record.patient_id)},
        )
        return record

    async def patient_history(self, session: AsyncSession, patient_id: str, limit: int = 50) -> list[dict]:
        limit = min(max(1, limit), self.settings.search_max_limit)
        rows = (
            (
                await session.execute(
                    select(DispensingRecord)
                    .where(
                        DispensingRecord.patient_id == uuid.UUID(patient_id),
                        DispensingRecord.deleted_at.is_(None),
                    )
                    .order_by(DispensingRecord.dispensed_at.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return [_disp_out(r) for r in rows]


# ---------------------------------------------------------------- serializers

def _med_out(m: Medication) -> dict:
    return {
        "id": str(m.id),
        "code": m.code,
        "name": m.name,
        "generic_name": m.generic_name,
        "strength": m.strength,
        "form": m.form,
        "controlled": m.controlled,
        "is_active": m.is_active,
    }


def _stock_out(s: StockLevel) -> dict:
    return {
        "id": str(s.id),
        "location": s.location,
        "batch_number": s.batch_number,
        "expiry_date": s.expiry_date.isoformat() if s.expiry_date else None,
        "quantity": float(s.quantity),
    }


def _disp_out(d: DispensingRecord) -> dict:
    return {
        "id": str(d.id),
        "patient_id": str(d.patient_id),
        "prescription_id": str(d.prescription_id) if d.prescription_id else None,
        "medication_id": str(d.medication_id),
        "quantity": float(d.quantity),
        "batch_number": d.batch_number,
        "price": float(d.price) if d.price is not None else None,
        "status": d.status,
        "dispensed_at": d.dispensed_at.isoformat() if d.dispensed_at else None,
        "returned_reason": d.returned_reason,
    }
