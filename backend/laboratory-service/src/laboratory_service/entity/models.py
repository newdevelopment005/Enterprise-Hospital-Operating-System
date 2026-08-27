import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from ehos_common.db import Base
from sqlalchemy import (
    JSON,
    TIMESTAMP,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class LabTest(Base):
    __tablename__ = "lab_tests"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    unit: Mapped[str | None] = mapped_column(String)
    reference_low: Mapped[Decimal | None] = mapped_column(Numeric)
    reference_high: Mapped[Decimal | None] = mapped_column(Numeric)
    specimen_type: Mapped[str | None] = mapped_column(String)
    turnaround_min: Mapped[int | None] = mapped_column()
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    audit_reference: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    deleted_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    deletion_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("code", name="uq_lab_tests_code"),
        Index("idx_lab_tests_category", "category"),
    )


class LabOrder(Base):
    __tablename__ = "lab_orders"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    patient_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    patient_snapshot: Mapped[dict | None] = mapped_column(JSON)
    encounter_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    ordering_doctor: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    priority: Mapped[str] = mapped_column(String, default="ROUTINE", nullable=False)
    ordered_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    clinical_notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="ORDERED", nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    audit_reference: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    deleted_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    deletion_reason: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list["LabOrderItem"]] = relationship("LabOrderItem", back_populates="order", lazy="selectin")
    samples: Mapped[list["Sample"]] = relationship("Sample", back_populates="order", lazy="selectin")

    __table_args__ = (
        CheckConstraint("priority IN ('ROUTINE','URGENT','STAT')", name="ck_lab_orders_priority"),
        CheckConstraint("status IN ('ORDERED','COLLECTED','IN_PROGRESS','RESULTED','VERIFIED','CANCELLED')", name="ck_lab_orders_status"),
        Index("idx_lab_orders_patient", "patient_id", "ordered_at"),
        Index("idx_lab_orders_doctor", "ordering_doctor"),
        Index("idx_lab_orders_encounter", "encounter_id"),
    )


class LabOrderItem(Base):
    __tablename__ = "lab_order_items"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    lab_order_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("lab_orders.id"), nullable=False)
    test_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("lab_tests.id"))
    test_name: Mapped[str] = mapped_column(String, nullable=False)
    specimen_type: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    audit_reference: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    deleted_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    deletion_reason: Mapped[str | None] = mapped_column(Text)

    order: Mapped["LabOrder"] = relationship("LabOrder", back_populates="items")
    results: Mapped[list["LabResult"]] = relationship("LabResult", back_populates="order_item", lazy="selectin")

    __table_args__ = (
        Index("idx_lab_order_items_order", "lab_order_id"),
        Index("idx_lab_order_items_test", "test_id"),
    )


class Sample(Base):
    __tablename__ = "samples"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    lab_order_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("lab_orders.id"), nullable=False)
    patient_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    barcode: Mapped[str] = mapped_column(String, nullable=False)
    sample_type: Mapped[str] = mapped_column(String, nullable=False)
    collection_time: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    collected_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    received_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    received_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    status: Mapped[str] = mapped_column(String, default="REQUESTED", nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    audit_reference: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    deleted_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    deletion_reason: Mapped[str | None] = mapped_column(Text)

    order: Mapped["LabOrder"] = relationship("LabOrder", back_populates="samples")
    results: Mapped[list["LabResult"]] = relationship("LabResult", back_populates="sample", lazy="selectin")

    __table_args__ = (
        CheckConstraint("status IN ('REQUESTED','COLLECTED','IN_TRANSIT','RECEIVED','ANALYZED','REJECTED','DISCARDED')", name="ck_samples_status"),
        UniqueConstraint("barcode", name="uq_samples_barcode"),
        Index("idx_samples_order", "lab_order_id"),
        Index("idx_samples_patient", "patient_id"),
    )


class LabResult(Base):
    __tablename__ = "lab_results"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    order_item_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("lab_order_items.id"), nullable=False)
    sample_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("samples.id"))
    patient_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    test_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("lab_tests.id"))
    test_name: Mapped[str] = mapped_column(String, nullable=False)
    result_numeric: Mapped[Decimal | None] = mapped_column(Numeric)
    result_text: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String)
    reference_range: Mapped[str | None] = mapped_column(String)
    flag: Mapped[str | None] = mapped_column(String)
    performed_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    performed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    verified_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    status: Mapped[str] = mapped_column(String, default="PRELIMINARY", nullable=False)
    instrumentation: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    audit_reference: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    deleted_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    deletion_reason: Mapped[str | None] = mapped_column(Text)

    order_item: Mapped["LabOrderItem"] = relationship("LabOrderItem", back_populates="results", lazy="selectin")
    sample: Mapped[Optional["Sample"]] = relationship("Sample", back_populates="results", lazy="selectin")

    __table_args__ = (
        CheckConstraint("flag IN ('NORMAL','HIGH','LOW','CRITICAL','ABNORMAL')", name="ck_lab_results_flag"),
        CheckConstraint("status IN ('PRELIMINARY','VERIFIED','AMENDED','CANCELLED')", name="ck_lab_results_status"),
        Index("idx_lab_results_patient", "patient_id", "performed_at"),
        Index("idx_lab_results_order", "order_item_id"),
        Index("idx_lab_results_sample", "sample_id"),
        Index("idx_lab_results_test", "test_id"),
    )
