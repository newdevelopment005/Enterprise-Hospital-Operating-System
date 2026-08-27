"""SQLAlchemy models for the queue-service.

Maps scheduling_db.queues + queue_entries (V001__init.sql) with the common
row block per DATABASE_DESIGN.md sections 2.5 and 5.2.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Declarative base for the queue-service."""


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


# JSONB on Postgres, JSON elsewhere (sqlite tests)
JSONType = JSON().with_variant(JSONB(), "postgresql")


class Queue(Base, CommonMixin):
    """A digital queue (OUTPATIENT, EMERGENCY, LAB, PHARMACY, ADMISSION, RADIOLOGY)."""

    __tablename__ = "queues"

    queue_type: Mapped[str] = mapped_column(String(20), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class QueueEntry(Base, CommonMixin):
    """A patient ticket inside a queue."""

    __tablename__ = "queue_entries"
    __table_args__ = (
        UniqueConstraint("queue_id", "ticket_number", name="uq_queue_entries_queue_ticket"),
    )

    queue_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    patient_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    ticket_number: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # NOTE: lifecycle state reuses CommonMixin.status (WAITING/CALLED/...) to
    # match scheduling_db.queue_entries.status in V001__init.sql.
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    served_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    wait_time_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
