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


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    states: Mapped[dict | None] = mapped_column(JSON)
    transitions: Mapped[dict | None] = mapped_column(JSON)
    initial_state: Mapped[str] = mapped_column(String, nullable=False)
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

    instances: Mapped[list["WorkflowInstance"]] = relationship("WorkflowInstance", back_populates="definition", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("key", "version", name="uq_wf_def_key_version"),
        Index("idx_wf_def_key", "key"),
    )


class WorkflowInstance(Base):
    __tablename__ = "workflow_instances"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    definition_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("workflow_definitions.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    patient_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    current_state: Mapped[str] = mapped_column(String, nullable=False)
    context: Mapped[dict | None] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    status: Mapped[str] = mapped_column(String, default="ACTIVE", nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    model_version: Mapped[int] = mapped_column(default=1, nullable=False)
    audit_reference: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    deleted_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    deletion_reason: Mapped[str | None] = mapped_column(Text)

    definition: Mapped["WorkflowDefinition"] = relationship("WorkflowDefinition", back_populates="instances", lazy="selectin")
    transitions: Mapped[list["WorkflowTransition"]] = relationship("WorkflowTransition", back_populates="instance", lazy="selectin")

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','COMPLETED','CANCELLED','PAUSED')", name="ck_wf_instance_status"),
        Index("idx_wf_inst_entity", "entity_type", "entity_id"),
        Index("idx_wf_inst_patient", "patient_id"),
        Index("idx_wf_inst_state", "current_state"),
    )


class WorkflowTransition(Base):
    __tablename__ = "workflow_transitions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    instance_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("workflow_instances.id"), nullable=False)
    from_state: Mapped[str] = mapped_column(String, nullable=False)
    to_state: Mapped[str] = mapped_column(String, nullable=False)
    event: Mapped[str] = mapped_column(String, nullable=False)
    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    event_metadata: Mapped[dict | None] = mapped_column("metadata", JSON)
    performed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
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

    instance: Mapped["WorkflowInstance"] = relationship("WorkflowInstance", back_populates="transitions", lazy="selectin")

    __table_args__ = (
        Index("idx_wf_trans_instance", "instance_id"),
        Index("idx_wf_trans_from", "from_state"),
        Index("idx_wf_trans_to", "to_state"),
    )
