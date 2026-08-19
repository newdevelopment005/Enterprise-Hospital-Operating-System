"""Application settings for the ehr-service.

Extends the shared ``ServiceSettings`` so the standard environment
(EHOS_ / POSTGRES_ / KAFKA_ vars, ``database_url``) is honoured, plus clinical
record defaults for notes, vitals and pagination.
"""

from __future__ import annotations

from functools import lru_cache

from ehos_common.config import ServiceSettings
from pydantic_settings import SettingsConfigDict


class EhrSettings(ServiceSettings):
    """Clinical record settings for the ehr-service."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- API defaults ---
    search_limit: int = 50
    search_max_limit: int = 200

    # --- Clinical defaults ---
    default_language: str = "en"
    max_note_content: int = 100_000
    max_history_entries: int = 500
    max_timeline_entries: int = 1000


@lru_cache
def get_settings() -> EhrSettings:
    """Build (and cache) the ehr-service settings."""
    settings = EhrSettings()  # type: ignore[call-arg]
    settings.service_name = "ehr-service"
    settings.database_name = "ehos_ehr"
    return settings