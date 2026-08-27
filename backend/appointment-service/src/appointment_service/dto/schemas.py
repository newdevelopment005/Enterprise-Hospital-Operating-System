"""Pydantic request schemas for the appointment-service with validation.

Validation rules:
- ``patient_id`` must be a UUID; optional ``provider_id``/``department_id`` too.
- ``start_time`` must be in the future at booking time (small clock skew
  tolerance); rescheduling also rejects past slots.
- ``duration_min`` is bounded by service settings defaults.
- enums mirror scheduling_db CHECK constraints (appointment_type, priority,
  source, status transitions).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CLOCK_SKEW_TOLERANCE = timedelta(minutes=1)

APPOINTMENT_TYPES = ("OUTPATIENT", "FOLLOWUP", "PROCEDURE", "TELEHEALTH")
PRIORITIES = ("ROUTINE", "URGENT", "EMERGENCY")
SOURCES = ("MANUAL", "PORTAL", "CALL", "KIOSK", "AI")
ACTIVE_STATUSES = ("SCHEDULED", "ARRIVED", "IN_PROGRESS")


def _parse_uuid(value: str | None, field_name: str) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid UUID") from exc


class AppointmentIn(BaseModel):
    """Booking request."""

    patient_id: str
    provider_id: str | None = None
    department_id: str | None = None
    appointment_type: str = Field(pattern="^(OUTPATIENT|FOLLOWUP|PROCEDURE|TELEHEALTH)$")
    start_time: datetime
    duration_min: int | None = Field(default=None, ge=5, le=480)
    reason: str | None = Field(default=None, max_length=2000)
    priority: str = Field(default="ROUTINE", pattern="^(ROUTINE|URGENT|EMERGENCY)$")
    source: str = Field(default="MANUAL", pattern="^(MANUAL|PORTAL|CALL|KIOSK|AI)$")
    consultation_room: str | None = Field(default=None, max_length=50)

    @field_validator("patient_id", "provider_id", "department_id")
    @classmethod
    def _uuids(cls, v: str | None, info) -> str | None:
        _parse_uuid(v, info.field_name)
        return v

    @model_validator(mode="after")
    def _future_start(self) -> AppointmentIn:
        now = datetime.now(UTC)
        start = self.start_time if self.start_time.tzinfo else self.start_time.replace(tzinfo=UTC)
        if start < now - CLOCK_SKEW_TOLERANCE:
            raise ValueError("Appointment start time cannot be in the past")
        return self


class RescheduleIn(BaseModel):
    """Move an existing appointment to a new slot."""

    start_time: datetime
    duration_min: int | None = Field(default=None, ge=5, le=480)

    @model_validator(mode="after")
    def _future_start(self) -> RescheduleIn:
        now = datetime.now(UTC)
        start = self.start_time if self.start_time.tzinfo else self.start_time.replace(tzinfo=UTC)
        if start < now - CLOCK_SKEW_TOLERANCE:
            raise ValueError("New appointment time cannot be in the past")
        return self


class CancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


# ---------------------------------------------------------------- output


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_id: str
    provider_id: str | None
    department_id: str | None
    appointment_type: str
    start_time: datetime
    end_time: datetime | None
    duration_min: int | None
    status: str
    reason: str | None
    priority: str
    source: str
    consultation_room: str | None
    cancellation_reason: str | None
    created_at: datetime
