from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---- Report Definition ----


class ReportDefinitionBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    report_type: str = Field(pattern="^(PATIENT_SUMMARY|FINANCIAL|CLINICAL|OPERATIONAL|REGULATORY)$")
    description: str | None = None
    parameters_schema: dict | None = None
    is_active: bool = True


class ReportDefinitionCreate(ReportDefinitionBase):
    pass


class ReportDefinitionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    parameters_schema: dict | None = None
    is_active: bool | None = None


class ReportDefinitionRead(ReportDefinitionBase):
    id: UUID
    status: str
    created_at: datetime
    updated_at: datetime
    model_version: int
    model_config = ConfigDict(from_attributes=True)


# ---- Report Instance ----


class ReportInstanceBase(BaseModel):
    report_definition_id: UUID
    parameters: dict | None = None
    requested_by: UUID


class ReportInstanceCreate(ReportInstanceBase):
    pass


class ReportInstanceRead(ReportInstanceBase):
    id: UUID
    status: str
    result_data: dict | None = None
    result_url: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    model_version: int
    model_config = ConfigDict(from_attributes=True)


# ---- Scheduled Report ----


class ScheduledReportBase(BaseModel):
    report_definition_id: UUID
    schedule_cron: str = Field(min_length=1, max_length=64)
    parameters: dict | None = None
    delivery_email: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class ScheduledReportCreate(ScheduledReportBase):
    pass


class ScheduledReportUpdate(BaseModel):
    schedule_cron: str | None = Field(default=None, min_length=1, max_length=64)
    parameters: dict | None = None
    delivery_email: str | None = None
    is_active: bool | None = None


class ScheduledReportRead(ScheduledReportBase):
    id: UUID
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
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
