"""Pydantic request schemas for the queue-service with validation.

Validation rules:
- ``queue_type`` mirrors the scheduling_db CHECK constraint.
- ``patient_id`` must be a UUID; ``priority`` is a small non-negative integer
  (higher = served first).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, field_validator


def _parse_uuid(value: str | None, field_name: str) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid UUID") from exc


class QueueIn(BaseModel):
    queue_type: str = Field(pattern="^(OUTPATIENT|EMERGENCY|LAB|PHARMACY|ADMISSION|RADIOLOGY)$")
    name: str | None = Field(default=None, max_length=100)
    department_id: str | None = None

    @field_validator("department_id")
    @classmethod
    def _dept(cls, v: str | None) -> str | None:
        _parse_uuid(v, "department_id")
        return v


class JoinIn(BaseModel):
    patient_id: str
    priority: int = Field(default=0, ge=0, le=9)
    patient_snapshot: dict | None = None

    @field_validator("patient_id")
    @classmethod
    def _pid(cls, v: str) -> str:
        _parse_uuid(v, "patient_id")
        return v


class PriorityIn(BaseModel):
    priority: int = Field(ge=0, le=9)
