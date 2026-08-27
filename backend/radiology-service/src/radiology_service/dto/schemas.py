from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---- Modality ----


class ModalityBase(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    is_active: bool = True


class ModalityCreate(ModalityBase):
    pass


class ModalityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    is_active: bool | None = None


class ModalityRead(ModalityBase):
    id: UUID
    status: str
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = ConfigDict(from_attributes=True)


# ---- RadiologyOrder ----


class RadiologyOrderBase(BaseModel):
    patient_id: UUID
    encounter_id: UUID | None = None
    ordering_doctor: UUID
    modality_code: str = Field(min_length=1, max_length=32)
    body_region: str = Field(min_length=1, max_length=128)
    clinical_indication: str | None = None
    priority: str = Field(default="ROUTINE", pattern="^(ROUTINE|URGENT|STAT)$")
    contrast: bool = False


class RadiologyOrderCreate(RadiologyOrderBase):
    pass


class RadiologyOrderUpdate(BaseModel):
    priority: str | None = Field(default=None, pattern="^(ROUTINE|URGENT|STAT)$")
    body_region: str | None = Field(default=None, min_length=1, max_length=128)
    clinical_indication: str | None = None
    contrast: bool | None = None
    status: str | None = Field(default=None, pattern="^(ORDERED|SCHEDULED|PERFORMING|COMPLETED|CANCELLED)$")


class RadiologyOrderRead(RadiologyOrderBase):
    id: UUID
    patient_snapshot: dict | None = None
    ordered_at: datetime
    scheduled_at: datetime | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = ConfigDict(from_attributes=True)


# ---- Study ----


class StudyBase(BaseModel):
    order_id: UUID
    patient_id: UUID
    modality_code: str = Field(min_length=1, max_length=32)
    body_region: str = Field(min_length=1, max_length=128)
    study_instance_uid: str | None = Field(default=None, max_length=128)
    accession_number: str | None = Field(default=None, max_length=64)


class StudyCreate(StudyBase):
    pass


class StudyStart(BaseModel):
    performed_by: UUID


class StudyComplete(BaseModel):
    technician_notes: str | None = None


class StudyRead(StudyBase):
    id: UUID
    performed_by: UUID | None = None
    performed_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: str
    technician_notes: str | None = None
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = ConfigDict(from_attributes=True)


# ---- RadiologyReport ----


class RadiologyReportBase(BaseModel):
    order_id: UUID
    patient_id: UUID
    study_id: UUID | None = None
    findings: str | None = None
    impression: str | None = None
    recommendation: str | None = None
    structured_report: dict | None = None


class RadiologyReportCreate(RadiologyReportBase):
    pass


class RadiologyReportUpdate(BaseModel):
    findings: str | None = None
    impression: str | None = None
    recommendation: str | None = None
    structured_report: dict | None = None
    status: str | None = Field(default=None, pattern="^(DRAFT|PRELIMINARY|FINAL|AMENDED|CANCELLED)$")


class RadiologyReportSign(BaseModel):
    signed_by: UUID


class RadiologyReportRead(RadiologyReportBase):
    id: UUID
    status: str
    signed_by: UUID | None = None
    signed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = ConfigDict(from_attributes=True)


# ---- Pagination ----


class PaginatedResponse(BaseModel):
    items: list
    total: int
    limit: int
    offset: int
