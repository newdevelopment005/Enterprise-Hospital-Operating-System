"""Application settings for the queue-service.

Extends the shared ``ServiceSettings`` so the standard environment
(EHOS_ / POSTGRES_ / KAFKA_ vars, ``database_url``) is honoured, plus
ticket-number formatting for the digital queues.
"""

from __future__ import annotations

from functools import lru_cache

from ehos_common.config import ServiceSettings
from pydantic_settings import SettingsConfigDict


class QueueSettings(ServiceSettings):
    """Digital-queue settings for the queue-service."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- Ticket numbers (per queue, e.g. OP-0001) ---
    ticket_width: int = 4

    # --- Listing ---
    search_max_limit: int = 200


@lru_cache
def get_settings() -> QueueSettings:
    """Build (and cache) the queue-service settings."""
    settings = QueueSettings()  # type: ignore[call-arg]
    settings.service_name = "queue-service"
    settings.database_name = "ehos_scheduling"  # shared scheduling_db per DATABASE_DESIGN.md 5.2
    return settings
