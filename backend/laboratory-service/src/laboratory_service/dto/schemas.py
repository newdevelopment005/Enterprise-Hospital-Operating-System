from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---- LabTest ----

class LabTestBase(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=100)
    unit: str | None = Field(default=None, max_length=32)
    reference_low: Decimal | None = None
    reference_high: Decimal | None = None
    specimen_type: str | None = Field(default=None, max_length=64)
    turnaround_min: int | None = Field(default=None, ge=0)
    is_active: bool = True


class LabTestCreate(LabTestBase):
    pass


class LabTestUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    unit: str | None = Field(default=None, max_length=32)
    reference_low: Decimal | None = None
    reference_high: Decimal | None = None
    specimen_type: str | None = Field(default=None, max_length=64)
    turnaround_min: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class LabTestRead(LabTestBase):
    id: UUID
    status: str
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = ConfigDict(from_attributes=True)


# ---- LabOrder ----

class LabOrderItemBase(BaseModel):
    test_id: UUID | None = None
    test_name: str = Field(min_length=1, max_length=255)
    specimen_type: str | None = Field(default=None, max_length=64)


class LabOrderItemCreate(LabOrderItemBase):
    pass


class LabOrderItemRead(LabOrderItemBase):
    id: UUID
    lab_order_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = ConfigDict(from_attributes=True)


class LabOrderBase(BaseModel):
    patient_id: UUID
    encounter_id: UUID | None = None
    ordering_doctor: UUID
    priority: str = Field(default="ROUTINE", pattern="^(ROUTINE|URGENT|STAT)$")
    clinical_notes: str | None = None


class LabOrderCreate(LabOrderBase):
    items: list[LabOrderItemCreate] = Field(min_length=1)


class LabOrderUpdate(BaseModel):
    priority: str | None = Field(default=None, pattern="^(ROUTINE|URGENT|STAT)$")
    clinical_notes: str | None = None
    status: str | None = Field(default=None, pattern="^(ORDERED|COLLECTED|IN_PROGRESS|RESULTED|VERIFIED|CANCELLED)$")


class LabOrderRead(LabOrderBase):
    id: UUID
    patient_snapshot: dict | None = None
    status: str
    ordered_at: datetime
    created_at: datetime
    updated_at: datetime
    version: int
    items: list[LabOrderItemRead] = []

    model_config = ConfigDict(from_attributes=True)


# ---- Sample ----

class SampleBase(BaseModel):
    lab_order_id: UUID
    patient_id: UUID
    barcode: str = Field(min_length=1, max_length=64)
    sample_type: str = Field(min_length=1, max_length=64)


class SampleCreate(SampleBase):
    pass


class SampleCollect(BaseModel):
    collected_by: UUID
    collection_time: datetime | None = None


class SampleReceive(BaseModel):
    received_by: UUID
    received_at: datetime | None = None


class SampleReject(BaseModel):
    rejection_reason: str = Field(min_length=1)


class SampleRead(SampleBase):
    id: UUID
    collection_time: datetime | None = None
    collected_by: UUID | None = None
    received_at: datetime | None = None
    received_by: UUID | None = None
    status: str
    rejection_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = ConfigDict(from_attributes=True)


# ---- LabResult ----

class LabResultBase(BaseModel):
    order_item_id: UUID
    sample_id: UUID | None = None
    patient_id: UUID
    test_id: UUID | None = None
    test_name: str = Field(min_length=1, max_length=255)
    result_numeric: Decimal | None = None
    result_text: str | None = None
    unit: str | None = Field(default=None, max_length=32)
    reference_range: str | None = Field(default=None, max_length=128)
    flag: str | None = Field(default=None, pattern="^(NORMAL|HIGH|LOW|CRITICAL|ABNORMAL)$")
    performed_by: UUID | None = None
    performed_at: datetime | None = None
    verified_by: UUID | None = None
    verified_at: datetime | None = None
    status: str = Field(default="PRELIMINARY", pattern="^(PRELIMINARY|VERIFIED|AMENDED|CANCELLED)$")
    instrumentation: str | None = Field(default=None, max_length=128)


class LabResultCreate(LabResultBase):
    pass


class LabResultUpdate(BaseModel):
    result_numeric: Decimal | None = None
    result_text: str | None = None
    unit: str | None = Field(default=None, max_length=32)
    reference_range: str | None = Field(default=None, max_length=128)
    flag: str | None = Field(default=None, pattern="^(NORMAL|HIGH|LOW|CRITICAL|ABNORMAL)$")
    performed_by: UUID | None = None
    performed_at: datetime | None = None
    status: str | None = Field(default=None, pattern="^(PRELIMINARY|VERIFIED|AMENDED|CANCELLED)$")
    instrumentation: str | None = Field(default=None, max_length=128)


class LabResultVerify(BaseModel):
    verified_by: UUID
    verified_at: datetime | None = None


class LabResultRead(LabResultBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = ConfigDict(from_attributes=True)


# ---- Pagination / List ----

class PaginatedResponse(BaseModel):
    items: list
    total: int
    limit: int
    offset: int
