"""Service settings loaded from environment variables.

Every service subclasses :class:`BaseSettings` via ``get_settings``/``Settings``.
Values are read from environment variables prefixed ``EHOS_`` and from the
deployment environment. Secrets must never be committed.
"""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceSettings(BaseSettings):
    """Common settings every EHOS service requires."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    service_name: str = "ehos-service"
    service_version: str = "0.1.0"
    environment: str = Field("development", alias="EHOS_ENV")
    log_level: str = Field("INFO", alias="EHOS_LOG_LEVEL")

    # --- Kafka ---
    kafka_bootstrap_servers: str = Field("localhost:9092", alias="KAFKA_BOOTSTRAP_SERVERS")

    # --- Database ---
    postgres_host: str = Field("localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(5432, alias="POSTGRES_PORT")
    postgres_user: str = Field("ehos", alias="POSTGRES_USER")
    postgres_password: str = Field("ehos", alias="POSTGRES_PASSWORD")
    database_name: str = "ehos"  # overridden per service

    # --- Redis ---
    redis_host: str = Field("localhost", alias="REDIS_HOST")
    redis_port: int = Field(6379, alias="REDIS_PORT")
    redis_password: str | None = Field(None, alias="REDIS_PASSWORD")

    # --- Identity / JWKS ---
    keycloak_url: str = Field("http://localhost:8080", alias="KEYCLOAK_URL")
    keycloak_realm: str = Field("ehos", alias="KEYCLOAK_REALM")

    @model_validator(mode="after")
    def _reject_default_credentials_outside_development(self) -> "ServiceSettings":
        """Fail fast if the built-in default DB password is used outside development.

        The default ``postgres_password`` exists only so a bare local checkout can
        run; silently accepting it in staging/production would connect to a real
        database with a publicly-known credential.
        """
        if self.postgres_password == "ehos" and self.environment.lower() != "development":  # noqa: S105
            raise ValueError(
                "POSTGRES_PASSWORD must be set to a strong, non-default value when "
                "EHOS_ENV is not 'development'"
            )
        return self

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy URL for this service's private database."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.database_name}"
        )

    @property
    def jwks_url(self) -> str:
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}/protocol/openid-connect/certs"

    @property
    def issuer(self) -> str:
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}"


@lru_cache
def get_settings(service_name: str | None = None, database_name: str | None = None) -> ServiceSettings:
    """Build and cache settings for a service.

    ``service_name`` and ``database_name`` are set explicitly from the service
    entrypoint so each service resolves to its own configuration.
    """
    settings = ServiceSettings()
    if service_name:
        settings.service_name = service_name
    if database_name:
        settings.database_name = database_name
    return settings