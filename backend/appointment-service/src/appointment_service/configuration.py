"""Application settings for the appointment-service.

Extends the shared ``ServiceSettings`` so the standard environment
(EHOS_ / POSTGRES_ / KAFKA_ vars, ``database_url``) is honoured, plus
clinic-hours and slot-grid tuning for availability generation.
"""

from __future__ import annotations

from functools import lru_cache

from ehos_common.config import ServiceSettings
from pydantic_settings import SettingsConfigDict


class AppointmentSettings(ServiceSettings):
    """Clinic scheduling settings for the appointment-service."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- Booking defaults ---
    default_duration_min: int = 30
    min_duration_min: int = 5
    max_duration_min: int = 480

    # --- Availability grid (local clinic hours, 24h clock) ---
    slot_minutes: int = 30
    clinic_open_hour: int = 8
    clinic_close_hour: int = 17

    # --- Listing ---
    search_max_limit: int = 200


@lru_cache
def get_settings() -> AppointmentSettings:
    """Build (and cache) the appointment-service settings."""
    settings = AppointmentSettings()  # type: ignore[call-arg]
    settings.service_name = "appointment-service"
    settings.database_name = "ehos_scheduling"
    return settings
