import uuid
from datetime import datetime
from typing import Optional
from uuid import UUID

from ehos_common.db import Base
from sqlalchemy import (
    JSON,
    TIMESTAMP,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Modality(Base):
    __tablename__ = "modalities"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
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
        UniqueConstraint("code", name="uq_modalities_code"),
    )


class RadiologyOrder(Base):
    __tablename__ = "radiology_orders"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    patient_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    patient_snapshot: Mapped[dict | None] = mapped_column(JSON)
    encounter_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    ordering_doctor: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    modality_code: Mapped[str] = mapped_column(String, nullable=False)
    body_region: Mapped[str] = mapped_column(String, nullable=False)
    clinical_indication: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String, default="ROUTINE", nullable=False)
    contrast: Mapped[bool] = mapped_column(default=False, nullable=False)
    ordered_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
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

    study: Mapped[Optional["Study"]] = relationship("Study", back_populates="order", uselist=False, lazy="selectin")
    reports: Mapped[list["RadiologyReport"]] = relationship("RadiologyReport", back_populates="order", lazy="selectin")

    __table_args__ = (
        CheckConstraint("priority IN ('ROUTINE','URGENT','STAT')", name="ck_rad_orders_priority"),
        CheckConstraint("status IN ('ORDERED','SCHEDULED','PERFORMING','COMPLETED','CANCELLED')", name="ck_rad_orders_status"),
        Index("idx_rad_orders_patient", "patient_id", "ordered_at"),
        Index("idx_rad_orders_doctor", "ordering_doctor"),
        Index("idx_rad_orders_modality", "modality_code"),
    )


class Study(Base):
    __tablename__ = "studies"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    order_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("radiology_orders.id"), nullable=False, unique=True)
    patient_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    modality_code: Mapped[str] = mapped_column(String, nullable=False)
    body_region: Mapped[str] = mapped_column(String, nullable=False)
    study_instance_uid: Mapped[str | None] = mapped_column(String)
    accession_number: Mapped[str | None] = mapped_column(String)
    performed_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    performed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    status: Mapped[str] = mapped_column(String, default="SCHEDULED", nullable=False)
    technician_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    audit_reference: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    deleted_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    deletion_reason: Mapped[str | None] = mapped_column(Text)

    order: Mapped["RadiologyOrder"] = relationship("RadiologyOrder", back_populates="study", lazy="selectin")

    __table_args__ = (
        CheckConstraint("status IN ('SCHEDULED','IN_PROGRESS','COMPLETED','CANCELLED')", name="ck_studies_status"),
        UniqueConstraint("study_instance_uid", name="uq_studies_instance_uid"),
        Index("idx_studies_order", "order_id"),
        Index("idx_studies_patient", "patient_id"),
    )


class RadiologyReport(Base):
    __tablename__ = "radiology_reports"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    order_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("radiology_orders.id"), nullable=False)
    patient_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    study_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("studies.id"))
    findings: Mapped[str | None] = mapped_column(Text)
    impression: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(Text)
    structured_report: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="DRAFT", nullable=False)
    signed_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    signed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    audit_reference: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    deleted_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    deletion_reason: Mapped[str | None] = mapped_column(Text)

    order: Mapped["RadiologyOrder"] = relationship("RadiologyOrder", back_populates="reports", lazy="selectin")

    __table_args__ = (
        CheckConstraint("status IN ('DRAFT','PRELIMINARY','FINAL','AMENDED','CANCELLED')", name="ck_rad_reports_status"),
        Index("idx_rad_reports_order", "order_id"),
        Index("idx_rad_reports_patient", "patient_id"),
        Index("idx_rad_reports_study", "study_id"),
    )
