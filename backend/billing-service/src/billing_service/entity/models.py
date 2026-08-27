"""SQLAlchemy models for the billing-service.

Maps billing_db (V001__init.sql): charges, invoices, invoice_items, payments,
receipts, adjustments. Financial records are never hard-deleted; corrections
go through adjustments/void flows. Common row block per DATABASE_DESIGN.md 2.5.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for the billing-service."""


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


Money = Numeric(12, 2, asdecimal=True)


class Charge(Base, CommonMixin):
    """A billable service line (consultation, lab, medication, room...)."""

    __tablename__ = "charges"

    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    service_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    item_type: Mapped[str] = mapped_column(String(30), nullable=False)
    item_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("1"))
    unit_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    discount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    source_service: Mapped[str] = mapped_column(String(50), nullable=False, default="MANUAL")
    billing_ref: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class Invoice(Base, CommonMixin):
    """An issued bill for a patient."""

    __tablename__ = "invoices"

    invoice_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    insurance_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    patient_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    paid_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    discount_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    tax_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="EGP")
    issued_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class InvoiceItem(Base, CommonMixin):
    """A charge snapshotted onto an invoice at issue time."""

    __tablename__ = "invoice_items"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("invoices.id"), index=True, nullable=False
    )
    charge_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("charges.id"), nullable=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("1"))
    unit_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)


class Payment(Base, CommonMixin):
    """Money received against an invoice."""

    __tablename__ = "payments"

    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("invoices.id"), index=True, nullable=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    received_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    refund_of: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class Receipt(Base, CommonMixin):
    """Proof of payment issued for a payment."""

    __tablename__ = "receipts"

    payment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payments.id"), index=True, nullable=False
    )
    receipt_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    issued_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    receipt_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Adjustment(Base, CommonMixin):
    """Correction entry against an invoice (never in-place edits)."""

    __tablename__ = "adjustments"

    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("invoices.id"), index=True, nullable=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    adjustment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    applied_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
