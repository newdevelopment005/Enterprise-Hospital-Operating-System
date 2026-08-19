"""Application settings for the EHOS prediction-service.

Extends the shared ``ServiceSettings``. All forecasting is local and offline:
no external model calls, no cloud services (PREDICTIVE_ANALYTICS_ARCHITECTURE
section 2, non-negotiable 1).
"""

from __future__ import annotations

from functools import lru_cache

from ehos_common.config import ServiceSettings
from pydantic_settings import SettingsConfigDict


class PredictionSettings(ServiceSettings):
    """Prediction-service settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Offline forecast adapters (seasonal-naive / SES) are the only available
    # families for this local PoC; extrapolation is advisory only.
    default_adapter: str = "seasonal_naive"
    default_period: int = 7
    default_horizon_steps: int = 7
    default_confidence: float = 0.90

    # Event bus
    event_source: str = "prediction-service"


@lru_cache
def get_settings() -> PredictionSettings:
    settings = PredictionSettings()
    settings.service_name = "prediction-service"
    settings.database_name = "ehos_ai"
    return settings