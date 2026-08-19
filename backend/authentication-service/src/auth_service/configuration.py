"""Application settings for the authentication-service.

Extends the shared ``ServiceSettings`` with JWT, session, MFA, password-policy
and lockout configuration. All values come from environment variables and are
never hardcoded or committed (CODING_STANDARDS.md section 15).

When no signing key is configured (development), an ephemeral RSA key pair is
generated at startup so the service can issue and verify JWTs out of the box.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from ehos_common.config import ServiceSettings


class AuthSettings(ServiceSettings):
    """Authentication-service specific settings."""

    # --- JWT / tokens ---
    jwt_algorithm: str = "RS256"           # RS256 (asymmetric) in all environments
    jwt_access_ttl_seconds: int = 900      # 15 minutes
    jwt_refresh_ttl_seconds: int = 2592000  # 30 days
    jwt_issuer: str = "http://localhost:8500"
    jwt_audience: str = "ehos-api"
    jwt_private_key_pem: str | None = None  # injected via AUTH_JWT_PRIVATE_KEY; ephemeral in dev
    jwt_public_key_pem: str | None = None
    jwt_keys_explicit: bool = False

    # --- Default role granted at self-service registration ---
    # Client-supplied roles are never honored; every registration receives the
    # default role below. Privileged roles must be granted by an administrator.
    register_default_role: str = "user"

    # --- MFA secret encryption ---
    # Dedicated Fernet key material for TOTP secrets. When unset, the JWT private
    # key is used; deriving from a *dev-only ephemeral* key in production is
    # refused (see mfa_service.py) because it breaks MFA across restarts.
    mfa_encryption_key: str | None = None

    # --- Session management ---
    session_idle_ttl_seconds: int = 43200   # 12 hours idle timeout
    max_sessions_per_user: int = 5

    # --- MFA ---
    mfa_issuer: str = "EHOS"
    mfa_window: int = 1                     # allowed +-1 step for clock skew
    mfa_challenge_ttl_seconds: int = 120    # login challenge valid 2 minutes

    # --- Password policy ---
    password_min_length: int = 12
    password_require_upper: bool = True
    password_require_lower: bool = True
    password_require_digit: bool = True
    password_require_special: bool = True
    password_history_size: int = 5          # cannot reuse last N passwords
    password_max_age_days: int = 90

    # --- Account lockout / brute force ---
    login_failure_limit: int = 5
    lockout_minutes: int = 15


@lru_cache
def get_settings() -> AuthSettings:
    """Build (and cache) the authentication-service settings.

    ``AuthSettings`` subclasses ``ServiceSettings``; constructing it directly
    keeps the service-specific JWT/MFA/password fields while reading the shared
    environment (EHOS_/POSTGRES_/KAFKA_ vars) via the base model configuration.
    """
    settings = AuthSettings()  # type: ignore[call-arg]
    settings.service_name = "authentication-service"
    settings.database_name = "ehos_identity"
    explicit = bool(settings.jwt_private_key_pem and settings.jwt_public_key_pem)
    _ensure_keys(settings)
    settings.jwt_keys_explicit = explicit
    return settings


def _ensure_keys(settings: AuthSettings) -> None:
    """Generate an ephemeral dev signing keypair when none is configured."""
    if settings.jwt_private_key_pem and settings.jwt_public_key_pem:
        return

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    settings.jwt_private_key_pem = private_pem
    settings.jwt_public_key_pem = public_pem