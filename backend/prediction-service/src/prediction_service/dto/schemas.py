"""Request/response DTOs for the prediction-service."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class TrainModelIn(BaseModel):
    """Train a candidate forecast model (P2+P3)."""

    target: str = Field(description="Forecast target key from the catalog, e.g. bed-occupancy")
    entity_type: str = "department"
    entity_id: str | None = None
    horizon: str = "7d"
    prediction_key: str | None = None
    adapter: str = "seasonal_naive"
    period: int = 7
    holdout: int | None = Field(default=None, ge=1, description="Validation hold-out steps")
    version: str | None = None
    series: list[float] = Field(min_length=1, description="Historical values (time-ordered)")
    dataset_ref: str | None = None
    approve: bool = False


class ApproveModelIn(BaseModel):
    """Owner approval (or rejection) of a registered model."""

    approver_id: str | None = None
    note: str | None = None


class PredictionIn(BaseModel):
    """Generate a forecast (P4)."""

    prediction_key: str | None = None
    entity_type: str = "department"
    entity_id: str | None = None
    horizon: str = "7d"
    adapter: str | None = None
    period: int = 7
    horizon_steps: int | None = Field(default=None, ge=1)
    window_from: date | None = None
    series: list[float] = Field(min_length=1, description="History (time-ordered)")


class ReconcileIn(BaseModel):
    """Actual-vs-forecast reconciliation (P5)."""

    prediction_key: str
    series: list[float] = Field(min_length=1, description="Actuals for the forecast window")


class ApproveResponse(BaseModel):
    success: bool = True
    data: dict
    statusCode: int = 200