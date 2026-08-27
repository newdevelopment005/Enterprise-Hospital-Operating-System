"""Analytics service settings for the EHOS executive dashboard."""

from __future__ import annotations

from functools import lru_cache

from ehos_common.config import ServiceSettings
from pydantic_settings import SettingsConfigDict


class AnalyticsSettings(ServiceSettings):
    """analytics-service settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Country used when no explicit country hint is provided by the caller.
    # "auto" resolves from request headers (X-Country / CF-IPCountry /
    # Accept-Language region), falling back to default_country_code.
    country_resolution: str = "auto"  # auto | fixed
    default_country_code: str = "EG"

    # Base currency all stored metric values are denominated in. Locale
    # endpoints convert to the resolved country's currency on read.
    base_currency: str = "USD"

    history_days: int = 30


@lru_cache
def get_settings() -> AnalyticsSettings:
    """Build (and cache) the analytics-service settings."""
    settings = AnalyticsSettings()  # type: ignore[call-arg]
    settings.service_name = "analytics-service"
    settings.database_name = "ehos_analytics"
    return settings
