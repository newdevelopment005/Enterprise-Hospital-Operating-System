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
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class ClinicalNote(Base):
    __tablename__ = "clinical_notes"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    patient_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    encounter_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    author_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    note_type: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String)
    content: Mapped[str | None] = mapped_column(Text)
    structured_data: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="DRAFT", nullable=False)
    signed_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    signed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    model_version: Mapped[int] = mapped_column(default=1, nullable=False)
    audit_reference: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    deleted_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    deletion_reason: Mapped[str | None] = mapped_column(Text)

    versions: Mapped[list["NoteVersion"]] = relationship("NoteVersion", back_populates="note", lazy="selectin")

    __table_args__ = (
        CheckConstraint(
            "note_type IN ('SOAP','PROGRESS','DISCHARGE','PROCEDURE','CONSULTATION','H&P','NURSING','CONSENT')",
            name="ck_note_type",
        ),
        CheckConstraint("status IN ('DRAFT','FINAL','AMENDED','CANCELLED')", name="ck_note_status"),
        Index("idx_notes_patient", "patient_id", "created_at"),
        Index("idx_notes_encounter", "encounter_id"),
        Index("idx_notes_author", "author_id"),
    )


class NoteVersion(Base):
    __tablename__ = "note_versions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    note_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("clinical_notes.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    structured_data: Mapped[dict | None] = mapped_column(JSON)
    changed_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text)
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

    note: Mapped["ClinicalNote"] = relationship("ClinicalNote", back_populates="versions", lazy="selectin")

    __table_args__ = (
        Index("idx_versions_note", "note_id"),
    )


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    note_type: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    structured_schema: Mapped[dict | None] = mapped_column(JSON)
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
        Index("idx_templates_type", "note_type"),
    )
