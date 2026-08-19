"""Application settings for the patient-service.

Extends the shared ``ServiceSettings`` so the standard environment
(EHOS_ / POSTGRES_ / KAFKA_ vars, ``database_url``) is honoured, plus
registry/search tuning specific to the MPI.
"""

from __future__ import annotations

from functools import lru_cache

from ehos_common.config import ServiceSettings
from pydantic_settings import SettingsConfigDict


class PatientSettings(ServiceSettings):
    """Registry and search settings for the patient-service."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- MPI registry ---
    mrn_prefix: str = "EH"                 # e.g. EH000001
    patient_number_prefix: str = "P"       # e.g. P0000001
    number_width: int = 6
    default_country: str = "TZ"

    # --- Search defaults ---
    search_limit: int = 50
    search_max_limit: int = 200


@lru_cache
def get_settings() -> PatientSettings:
    """Build (and cache) the patient-service settings."""
    settings = PatientSettings()  # type: ignore[call-arg]
    settings.service_name = "patient-service"
    settings.database_name = "ehos_patient"
    return settings