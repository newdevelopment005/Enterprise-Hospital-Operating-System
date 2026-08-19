"""Pydantic schemas for the audit-service."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AuditRecordCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=255)
    actor_id: str | None = Field(default=None, max_length=255)
    correlation_id: str | None = Field(default=None, max_length=64)
    source: str = Field(min_length=1, max_length=255)
    ip_address: str | None = Field(default=None, max_length=64)
    action: str | None = Field(default=None, max_length=255)
    resource_type: str | None = Field(default=None, max_length=255)
    resource_id: str | None = Field(default=None, max_length=255)
    old_value: str | None = None
    new_value: str | None = None
    reason: str | None = None
    occurred_at: datetime | None = None


class AuditRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: str
    event_type: str
    actor_id: str | None
    correlation_id: str | None
    source: str
    ip_address: str | None
    action: str | None
    resource_type: str | None
    resource_id: str | None
    old_value: str | None
    new_value: str | None
    reason: str | None
    occurred_at: datetime
    created_at: datetime
    content_hash: str
    previous_hash: str | None


class AuditQuery(BaseModel):
    event_type: str | None = None
    actor_id: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)