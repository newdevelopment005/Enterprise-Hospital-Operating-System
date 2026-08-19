"""Channel transport settings for the notification-service.

Real delivery is opt-in via ``NOTIFICATIONS_TRANSPORT``:

- ``log`` (default): adapters record deliveries into the log and return a
  deterministic mock message id — safe for local dev and no external credentials.
- ``smtp``: ``EmailAdapter`` sends through a real SMTP relay using the standard
  library (AUTH/TLS from env). ``SmsAdapter``/``PushAdapter`` still log.
- ``http``: ``SmsAdapter``/``PushAdapter`` post to a provider HTTP endpoint;
  ``EmailAdapter`` falls back to ``smtp`` configuration.

The transport switch lives here so the core ``NotificationService`` and its
tests stay agnostic.
"""

from __future__ import annotations

from functools import lru_cache

from ehos_common.config import ServiceSettings
from pydantic_settings import SettingsConfigDict


class NotificationSettings(ServiceSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # log (default) | smtp | http
    notifications_transport: str = "log"

    # Fallback recipient for events whose payload carries no contact channel
    # (e.g. PatientRegistered). In real deployments point this at the desk,
    # agent, or fan-out address that should be notified.
    admission_inbox: str = "admissions@ehos.example"

    # --- SMTP ---
    smtp_host: str = "localhost"
    smtp_port: int = 25
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    smtp_from: str = "noreply@ehos.example"
    smtp_timeout: float = 10.0

    # --- HTTP provider (SMS / push webhooks) ---
    sms_http_url: str | None = None
    sms_http_token: str | None = None
    push_http_url: str | None = None
    push_http_token: str | None = None

    @property
    def smtp_enabled(self) -> bool:
        return self.notifications_transport == "smtp"

    @property
    def http_enabled(self) -> bool:
        return self.notifications_transport == "http"


@lru_cache
def get_settings() -> NotificationSettings:
    """Build (and cache) the notification-service settings."""
    settings = NotificationSettings()  # type: ignore[call-arg]
    settings.service_name = "notification-service"
    settings.database_name = "ehos_notification"
    return settings