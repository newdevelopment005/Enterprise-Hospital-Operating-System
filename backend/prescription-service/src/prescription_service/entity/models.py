"""SQLAlchemy models for the prescription-service.

Maps prescription_db (V001__init.sql): prescriptions, prescription_items,
medication_administration, patient_allergies. Common row block per
DATABASE_DESIGN.md section 2.5.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Declarative base for the prescription-service."""


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class CommonMixin:
    """Common row block (id uuid, audit fields, version, status, soft delete)."""

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ACTIVE")
    audit_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    deletion_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


JSONType = JSON().with_variant(JSONB(), "postgresql")


class Prescription(Base, CommonMixin):
    """Prescription header with allergy/interaction safety flags."""

    __tablename__ = "prescriptions"

    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    patient_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    prescriber_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    therapy_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    allergy_checked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    interaction_checked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    repeat_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class PrescriptionItem(Base, CommonMixin):
    """One medication line on a prescription."""

    __tablename__ = "prescription_items"

    prescription_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("prescriptions.id"), index=True, nullable=False
    )
    medication_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    medication: Mapped[str] = mapped_column(String(255), nullable=False)
    dosage: Mapped[str] = mapped_column(String(100), nullable=False)
    frequency: Mapped[str] = mapped_column(String(100), nullable=False)
    route: Mapped[str | None] = mapped_column(String(50), nullable=True)
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 2, asdecimal=True), nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_per_day: Mapped[Decimal | None] = mapped_column(Numeric(12, 2, asdecimal=True), nullable=True)


class MedicationAdministration(Base, CommonMixin):
    """MAR entry: one administration (or refusal/miss) of a prescribed item."""

    __tablename__ = "medication_administration"

    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    prescription_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    prescription_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("prescription_items.id"), index=True, nullable=True
    )
    medication_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    medication: Mapped[str] = mapped_column(String(255), nullable=False)
    dose: Mapped[str] = mapped_column(String(100), nullable=False)
    route: Mapped[str | None] = mapped_column(String(50), nullable=True)
    administered_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    administered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    documented_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    batch_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason_not_given: Mapped[str | None] = mapped_column(Text, nullable=True)
    witness_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class PatientAllergy(Base, CommonMixin):
    """Patient-recorded allergy (drug allergies drive prescribing checks)."""

    __tablename__ = "patient_allergies"
    __table_args__ = (
        UniqueConstraint("patient_id", "allergen", "allergen_type", name="uq_patient_allergies_patient_allergen"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    allergen: Mapped[str] = mapped_column(String(255), nullable=False)
    allergen_type: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    reaction: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
