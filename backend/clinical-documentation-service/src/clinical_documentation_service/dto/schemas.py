from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---- ClinicalNote ----


class ClinicalNoteBase(BaseModel):
    patient_id: UUID
    encounter_id: UUID | None = None
    author_id: UUID
    note_type: str = Field(pattern="^(SOAP|PROGRESS|DISCHARGE|PROCEDURE|CONSULTATION|H&P|NURSING|CONSENT)$")
    title: str | None = Field(default=None, max_length=255)
    content: str | None = None
    structured_data: dict | None = None


class ClinicalNoteCreate(ClinicalNoteBase):
    pass


class ClinicalNoteUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    content: str | None = None
    structured_data: dict | None = None
    status: str | None = Field(default=None, pattern="^(DRAFT|FINAL|AMENDED|CANCELLED)$")


class ClinicalNoteSign(BaseModel):
    signed_by: UUID


class ClinicalNoteRead(ClinicalNoteBase):
    id: UUID
    status: str
    signed_by: UUID | None = None
    signed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    model_version: int

    model_config = ConfigDict(from_attributes=True)


# ---- NoteVersion ----


class NoteVersionRead(BaseModel):
    id: UUID
    note_id: UUID
    version_number: int
    content: str | None = None
    structured_data: dict | None = None
    changed_by: UUID
    change_summary: str | None = None
    created_at: datetime
    status: str
    model_version: int

    model_config = ConfigDict(from_attributes=True)


# ---- Template ----


class TemplateBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    note_type: str = Field(pattern="^(SOAP|PROGRESS|DISCHARGE|PROCEDURE|CONSULTATION|H&P|NURSING|CONSENT)$")
    content: str | None = None
    structured_schema: dict | None = None
    is_active: bool = True


class TemplateCreate(TemplateBase):
    pass


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    content: str | None = None
    structured_schema: dict | None = None
    is_active: bool | None = None


class TemplateRead(TemplateBase):
    id: UUID
    status: str
    created_at: datetime
    updated_at: datetime
    model_version: int

    model_config = ConfigDict(from_attributes=True)


# ---- Pagination ----


class PaginatedResponse(BaseModel):
    items: list
    total: int
    limit: int
    offset: int
