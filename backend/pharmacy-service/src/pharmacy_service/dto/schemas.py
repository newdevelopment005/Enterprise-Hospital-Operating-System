"""Pydantic request schemas for the pharmacy-service with validation."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator


def _parse_uuid(value: str | None, field_name: str) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid UUID") from exc


class MedicationIn(BaseModel):
    code: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=2, max_length=255)
    generic_name: str | None = Field(default=None, max_length=255)
    manufacturer: str | None = Field(default=None, max_length=255)
    strength: str | None = Field(default=None, max_length=50)
    form: str | None = Field(default=None, max_length=50)
    controlled: bool = False
    atc_code: str | None = Field(default=None, max_length=20)


class StockReceiveIn(BaseModel):
    medication_id: str
    location: str = Field(default="MAIN", max_length=50)
    batch_number: str = Field(min_length=1, max_length=100)
    expiry_date: date
    quantity: Decimal = Field(gt=0)

    @field_validator("medication_id")
    @classmethod
    def _mid(cls, v: str) -> str:
        _parse_uuid(v, "medication_id")
        return v

    @model_validator(mode="after")
    def _not_expired(self) -> StockReceiveIn:
        if self.expiry_date <= date.today():
            raise ValueError("Cannot receive stock that is already expired")
        return self


class DispenseIn(BaseModel):
    patient_id: str
    medication_id: str
    quantity: Decimal = Field(gt=0)
    location: str = Field(default="MAIN", max_length=50)
    prescription_id: str | None = None
    prescription_item_id: str | None = None
    dispensed_by: str
    witness_id: str | None = None  # REQUIRED for controlled drugs
    price: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator(
        "patient_id", "medication_id", "prescription_id",
        "prescription_item_id", "dispensed_by", "witness_id",
    )
    @classmethod
    def _uuids(cls, v: str | None, info) -> str | None:
        _parse_uuid(v, info.field_name)
        return v


class ReturnIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
