"""Pydantic request schemas for the prescription-service with validation.

Validation rules:
- medication lines require name, dosage and frequency.
- ``override_flags`` allows prescribing despite an allergy conflict; the
  conflict is still recorded (allergy_checked stays true and the conflict
  list is stored on the audit reference).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator


def _parse_uuid(value: str | None, field_name: str) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid UUID") from exc


class ItemIn(BaseModel):
    medication: str = Field(min_length=2, max_length=255)
    medication_id: str | None = None
    dosage: str = Field(min_length=1, max_length=100)
    frequency: str = Field(min_length=1, max_length=100)
    route: str | None = Field(default=None, max_length=50)
    duration_days: int | None = Field(default=None, ge=1, le=365)
    quantity: Decimal | None = Field(default=None, ge=0)
    instructions: str | None = Field(default=None, max_length=2000)
    max_per_day: Decimal | None = Field(default=None, ge=0)

    @field_validator("medication_id")
    @classmethod
    def _mid(cls, v: str | None) -> str | None:
        _parse_uuid(v, "medication_id")
        return v


class PrescriptionIn(BaseModel):
    patient_id: str
    prescriber_id: str
    encounter_id: str | None = None
    therapy_type: str = Field(default="ACUTE", pattern="^(ACUTE|CHRONIC|PRN|PROPHYLACTIC)$")
    start_date: date | None = None
    end_date: date | None = None
    repeat_instructions: str | None = Field(default=None, max_length=2000)
    reason: str | None = Field(default=None, max_length=2000)
    items: list[ItemIn] = Field(min_length=1)
    # prescribe even when a drug-allergy conflict is detected (recorded!)
    override_flags: bool = False

    @field_validator("patient_id", "prescriber_id", "encounter_id")
    @classmethod
    def _uuids(cls, v: str | None, info) -> str | None:
        _parse_uuid(v, info.field_name)
        return v

    @model_validator(mode="after")
    def _dates(self) -> PrescriptionIn:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class CancelIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class AdministrationIn(BaseModel):
    prescription_item_id: str
    administered_by: str
    administered_at: datetime | None = None
    dose: str | None = Field(default=None, max_length=100)
    route: str | None = Field(default=None, max_length=50)
    batch_number: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)
    reason_not_given: str | None = Field(default=None, max_length=500)
    witness_id: str | None = None
    mar_status: str = Field(default="GIVEN", pattern="^(GIVEN|REFUSED|MISSED|PARTIAL|HELD)$")

    @field_validator(
        "prescription_item_id", "administered_by", "witness_id"
    )
    @classmethod
    def _uuids(cls, v: str | None, info) -> str | None:
        _parse_uuid(v, info.field_name)
        return v


class AllergyIn(BaseModel):
    patient_id: str
    allergen: str = Field(min_length=2, max_length=255)
    allergen_type: str = Field(pattern="^(DRUG|FOOD|ENVIRONMENT|OTHER)$")
    severity: str = Field(pattern="^(MILD|MODERATE|SEVERE)$")
    reaction: str | None = Field(default=None, max_length=2000)
    recorded_by: str
    confirmed: bool = False

    @field_validator("patient_id", "recorded_by")
    @classmethod
    def _uuids(cls, v: str, info) -> str:
        _parse_uuid(v, info.field_name)
        return v
