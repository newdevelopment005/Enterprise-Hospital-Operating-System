from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---- Coverage ----


class CoverageBase(BaseModel):
    patient_id: UUID
    payer_name: str = Field(min_length=1, max_length=255)
    plan_name: str | None = Field(default=None, max_length=255)
    policy_number: str = Field(min_length=1, max_length=128)
    group_number: str | None = Field(default=None, max_length=128)
    coverage_type: str = Field(pattern="^(HEALTH|DENTAL|VISION|PRESCRIPTION|MENTAL_HEALTH)$")
    effective_date: str
    termination_date: str | None = None
    copay: float | None = Field(default=None, ge=0)
    deductible: float | None = Field(default=None, ge=0)
    coinsurance: float | None = Field(default=None, ge=0, le=1)
    is_active: bool = True


class CoverageCreate(CoverageBase):
    pass


class CoverageUpdate(BaseModel):
    payer_name: str | None = Field(default=None, min_length=1, max_length=255)
    plan_name: str | None = None
    policy_number: str | None = Field(default=None, min_length=1, max_length=128)
    group_number: str | None = None
    effective_date: str | None = None
    termination_date: str | None = None
    copay: float | None = None
    deductible: float | None = None
    coinsurance: float | None = None
    is_active: bool | None = None


class CoverageRead(CoverageBase):
    id: UUID
    status: str
    created_at: datetime
    updated_at: datetime
    model_version: int
    model_config = ConfigDict(from_attributes=True)


# ---- Claim ----


class ClaimBase(BaseModel):
    patient_id: UUID
    coverage_id: UUID
    encounter_id: UUID | None = None
    service_date: str
    diagnosis_codes: list[str] | None = None
    procedure_codes: list[str] | None = None
    total_amount: float = Field(ge=0)


class ClaimCreate(ClaimBase):
    pass


class ClaimUpdate(BaseModel):
    approved_amount: float | None = Field(default=None, ge=0)
    paid_amount: float | None = Field(default=None, ge=0)
    patient_responsibility: float | None = Field(default=None, ge=0)
    status: str | None = Field(
        default=None,
        pattern="^(DRAFT|SUBMITTED|REVIEWING|APPROVED|PARTIAL|DENIED|APPEALED|PAID|VOID)$",
    )
    denial_reason: str | None = None


class ClaimRead(ClaimBase):
    id: UUID
    approved_amount: float | None = None
    paid_amount: float | None = None
    patient_responsibility: float | None = None
    status: str
    denial_reason: str | None = None
    submitted_at: datetime | None = None
    adjudicated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    model_version: int
    model_config = ConfigDict(from_attributes=True)


# ---- Prior Authorization ----


class PriorAuthBase(BaseModel):
    patient_id: UUID
    coverage_id: UUID
    service_type: str = Field(min_length=1, max_length=128)
    procedure_codes: list[str] | None = None
    clinical_justification: str | None = None
    requested_by: UUID


class PriorAuthCreate(PriorAuthBase):
    pass


class PriorAuthDecision(BaseModel):
    decision: str = Field(pattern="^(APPROVED|DENIED)$")
    approved_units: int | None = Field(default=None, ge=1)
    valid_from: str | None = None
    valid_to: str | None = None
    denial_reason: str | None = None
    decided_by: UUID


class PriorAuthRead(PriorAuthBase):
    id: UUID
    status: str
    decision: str | None = None
    approved_units: int | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    decided_by: UUID | None = None
    decided_at: datetime | None = None
    denial_reason: str | None = None
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
