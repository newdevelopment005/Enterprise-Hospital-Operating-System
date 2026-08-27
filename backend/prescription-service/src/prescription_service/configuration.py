"""Application settings for the prescription-service."""

from __future__ import annotations

from functools import lru_cache

from ehos_common.config import ServiceSettings
from pydantic_settings import SettingsConfigDict


class PrescriptionSettings(ServiceSettings):
    """Prescribing settings for the prescription-service."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- Safety limits ---
    max_items_per_prescription: int = 20
    search_max_limit: int = 200


@lru_cache
def get_settings() -> PrescriptionSettings:
    """Build (and cache) the prescription-service settings."""
    settings = PrescriptionSettings()  # type: ignore[call-arg]
    settings.service_name = "prescription-service"
    settings.database_name = "ehos_prescription"
    return settings
