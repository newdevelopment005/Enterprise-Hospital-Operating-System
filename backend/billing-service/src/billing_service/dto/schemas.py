"""Pydantic request schemas for the billing-service with validation.

Validation rules:
- money fields must be >= 0; payment amount must be > 0.
- enums mirror billing_db CHECK constraints.
- UUID-shaped string fields are validated early with clear messages.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

PAYMENT_METHODS = ("CASH", "CARD", "WALLET", "BANK", "INSURANCE", "ONLINE")
ADJUSTMENT_TYPES = ("DISCOUNT", "REBATE", "VOID", "CORRECTION", "WRITE_OFF")


def _parse_uuid(value: str | None, field_name: str) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid UUID") from exc


class ChargeIn(BaseModel):
    patient_id: str
    encounter_id: str | None = None
    item_type: str = Field(pattern="^(CONSULTATION|LAB|RADIOLOGY|MEDICATION|PROCEDURE|ROOM|OTHER)$")
    item_code: str | None = Field(default=None, max_length=50)
    description: str = Field(min_length=2, max_length=2000)
    quantity: Decimal = Field(default=Decimal("1"), ge=0)
    unit_price: Decimal = Field(ge=0)
    discount: Decimal = Field(default=Decimal("0"), ge=0)

    @field_validator("patient_id", "encounter_id")
    @classmethod
    def _uuids(cls, v: str | None, info) -> str | None:
        _parse_uuid(v, info.field_name)
        return v


class InvoiceIn(BaseModel):
    """Issue an invoice; charge_ids omitted means all PENDING charges."""

    patient_id: str
    charge_ids: list[str] = Field(default_factory=list)
    insurance_amount: Decimal = Field(default=Decimal("0"), ge=0)
    due_date: date | None = None

    @field_validator("patient_id")
    @classmethod
    def _pid(cls, v: str) -> str:
        _parse_uuid(v, "patient_id")
        return v


class PaymentIn(BaseModel):
    invoice_id: str
    amount: Decimal = Field(gt=0)
    payment_method: str = Field(pattern="^(CASH|CARD|WALLET|BANK|INSURANCE|ONLINE)$")
    provider_ref: str | None = Field(default=None, max_length=255)

    @field_validator("invoice_id")
    @classmethod
    def _iid(cls, v: str) -> str:
        _parse_uuid(v, "invoice_id")
        return v


class AdjustmentIn(BaseModel):
    invoice_id: str
    adjustment_type: str = Field(pattern="^(DISCOUNT|REBATE|VOID|CORRECTION|WRITE_OFF)$")
    amount: Decimal = Field(ge=0)
    reason: str = Field(min_length=3, max_length=2000)

    @field_validator("invoice_id")
    @classmethod
    def _iid(cls, v: str) -> str:
        _parse_uuid(v, "invoice_id")
        return v


class VoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
