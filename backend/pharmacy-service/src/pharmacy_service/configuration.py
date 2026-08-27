"""Application settings for the pharmacy-service."""

from __future__ import annotations

from functools import lru_cache

from ehos_common.config import ServiceSettings
from pydantic_settings import SettingsConfigDict


class PharmacySettings(ServiceSettings):
    """Pharmacy settings for the pharmacy-service."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- Stock defaults ---
    default_location: str = "MAIN"
    expiry_warning_days: int = 90
    low_stock_threshold: float = 10.0
    search_max_limit: int = 200


@lru_cache
def get_settings() -> PharmacySettings:
    """Build (and cache) the pharmacy-service settings."""
    settings = PharmacySettings()  # type: ignore[call-arg]
    settings.service_name = "pharmacy-service"
    settings.database_name = "ehos_pharmacy"
    return settings
