import uuid
from datetime import datetime
from typing import Optional
from uuid import UUID

from ehos_common.db import Base
from sqlalchemy import (
    JSON,
    TIMESTAMP,
    CheckConstraint,
    Float,
    Index,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Coverage(Base):
    __tablename__ = "coverage"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    patient_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    payer_name: Mapped[str] = mapped_column(String, nullable=False)
    plan_name: Mapped[str | None] = mapped_column(String)
    policy_number: Mapped[str] = mapped_column(String, nullable=False)
    group_number: Mapped[str | None] = mapped_column(String)
    coverage_type: Mapped[str] = mapped_column(String, nullable=False)
    effective_date: Mapped[str] = mapped_column(String, nullable=False)
    termination_date: Mapped[str | None] = mapped_column(String)
    copay: Mapped[float | None] = mapped_column(Float)
    deductible: Mapped[float | None] = mapped_column(Float)
    coinsurance: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    model_version: Mapped[int] = mapped_column(default=1, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    audit_reference: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    deleted_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    deletion_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "coverage_type IN ('HEALTH','DENTAL','VISION','PRESCRIPTION','MENTAL_HEALTH')",
            name="ck_coverage_type",
        ),
        Index("idx_coverage_patient", "patient_id", "is_active"),
    )


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    patient_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    coverage_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    encounter_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    service_date: Mapped[str] = mapped_column(String, nullable=False)
    diagnosis_codes: Mapped[list | None] = mapped_column(JSON)
    procedure_codes: Mapped[list | None] = mapped_column(JSON)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    approved_amount: Mapped[float | None] = mapped_column(Float)
    paid_amount: Mapped[float | None] = mapped_column(Float)
    patient_responsibility: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String, default="DRAFT", nullable=False)
    denial_reason: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    adjudicated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    model_version: Mapped[int] = mapped_column(default=1, nullable=False)
    audit_reference: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    deleted_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    deletion_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','REVIEWING','APPROVED','PARTIAL','DENIED','APPEALED','PAID','VOID')",
            name="ck_claim_status",
        ),
        Index("idx_claims_patient", "patient_id", "created_at"),
        Index("idx_claims_coverage", "coverage_id"),
    )


class PriorAuthorization(Base):
    __tablename__ = "prior_authorizations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    patient_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    coverage_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    service_type: Mapped[str] = mapped_column(String, nullable=False)
    procedure_codes: Mapped[list | None] = mapped_column(JSON)
    clinical_justification: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String, default="PENDING", nullable=False)
    decision: Mapped[str | None] = mapped_column(String)
    approved_units: Mapped[int | None] = mapped_column()
    valid_from: Mapped[str | None] = mapped_column(String)
    valid_to: Mapped[str | None] = mapped_column(String)
    decided_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    denial_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    model_version: Mapped[int] = mapped_column(default=1, nullable=False)
    audit_reference: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    deleted_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    deletion_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','SUBMITTED','APPROVED','DENIED','EXPIRED','CANCELLED')",
            name="ck_pauth_status",
        ),
        Index("idx_pauth_patient", "patient_id"),
    )
