"""SQLAlchemy models for the pharmacy-service.

Maps pharmacy_db (V001__init.sql): medications, stock_levels,
dispensing_records, controlled_drug_log. Common row block per
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
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Declarative base for the pharmacy-service."""


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
Qty = Numeric(12, 2, asdecimal=True)


class Medication(Base, CommonMixin):
    """Catalog entry; ``controlled`` marks drugs of addiction (2-person rule)."""

    __tablename__ = "medications"

    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    generic_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    strength: Mapped[str | None] = mapped_column(String(50), nullable=True)
    form: Mapped[str | None] = mapped_column(String(50), nullable=True)  # TABLET/SYRUP/INJECTION...
    controlled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    atc_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    attributes: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class StockLevel(Base, CommonMixin):
    """On-hand quantity for one (medication, location, batch)."""

    __tablename__ = "stock_levels"

    medication_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("medications.id"), index=True, nullable=False
    )
    location: Mapped[str] = mapped_column(String(50), nullable=False, default="MAIN")
    quantity: Mapped[Decimal] = mapped_column(Qty, nullable=False, default=Decimal("0"))
    reserved: Mapped[Decimal] = mapped_column(Qty, nullable=False, default=Decimal("0"))
    batch_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class DispensingRecord(Base, CommonMixin):
    """One issue of medication to a patient (optionally against a prescription)."""

    __tablename__ = "dispensing_records"

    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    prescription_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    prescription_item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    medication_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("medications.id"), index=True, nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    dispensed_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    dispensed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    batch_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2, asdecimal=True), nullable=True)
    charge_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    returned_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # lifecycle reuses CommonMixin.status: PREPARED/DISPENSED/PICKED_UP/RETURNED/...


class ControlledDrugLog(Base, CommonMixin):
    """Immutable register for controlled drugs (actor + witness, running balance)."""

    __tablename__ = "controlled_drug_log"

    medication_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("medications.id"), index=True, nullable=False
    )
    batch_number: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # RECEIVED/ISSUED/RETURNED/DISCARDED/COUNT
    quantity: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    witness_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    balance_check: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
