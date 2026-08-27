"""Application settings for the billing-service.

Extends the shared ``ServiceSettings`` plus document-number formatting and
default currency for the billing domain.
"""

from __future__ import annotations

from functools import lru_cache

from ehos_common.config import ServiceSettings
from pydantic_settings import SettingsConfigDict


class BillingSettings(ServiceSettings):
    """Billing settings for the billing-service."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- Document numbers ---
    invoice_prefix: str = "INV"
    receipt_prefix: str = "RCPT"
    number_width: int = 6

    # --- Defaults ---
    currency: str = "EGP"

    # --- Listing ---
    search_max_limit: int = 200


@lru_cache
def get_settings() -> BillingSettings:
    """Build (and cache) the billing-service settings."""
    settings = BillingSettings()  # type: ignore[call-arg]
    settings.service_name = "billing-service"
    settings.database_name = "ehos_billing"
    return settings
