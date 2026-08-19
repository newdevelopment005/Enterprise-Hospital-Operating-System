"""JWT access-token issuance/validation and opaque refresh-token lifecycle.

Access tokens are RS256 JWTs with standard OIDC claims (``sub``, ``iss``, ``aud``,
``iat``, ``exp``, ``jti``, ``realm_access``, ``scope``) so the API gateway and other
services can validate them (SSO-ready). Refresh tokens are opaque random values
stored only as SHA-256 hashes; they rotate on every use to detect reuse.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from pydantic import BaseModel

from auth_service.configuration import AuthSettings
from auth_service.entity.models import User


class TokenError(Exception):
    """Raised when a token is invalid, expired, revoked, or reused."""


class TokenClaims(BaseModel):
    sub: str
    username: str
    jti: str
    session_id: str
    roles: list[str]
    permissions: list[str]
    scope: str = "openid profile email"


class TokenService:
    """Issues and validates access JWTs; manages refresh-token hashing."""

    def __init__(self, settings: AuthSettings):
        self.settings = settings
        self._private_key = settings.jwt_private_key_pem
        self._public_key = settings.jwt_public_key_pem

    # ------------------------------------------------------------ access JWT

    def issue_access_token(
        self,
        user: User,
        session_id: uuid.UUID,
        roles: list[str],
        permissions: list[str],
        scope: str = "openid profile email",
    ) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": str(user.id),
            "username": user.username,
            "email": user.email,
            "given_name": user.given_name,
            "family_name": user.family_name,
            "iss": self.settings.jwt_issuer,
            "aud": self.settings.jwt_audience,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=self.settings.jwt_access_ttl_seconds)).timestamp()),
            "jti": str(uuid.uuid4()),
            "session_id": str(session_id),
            "scope": scope,
            "realm_access": {"roles": roles},
            "permissions": permissions,
        }
        return jwt.encode(payload, self._private_key, algorithm=self.settings.jwt_algorithm)

    def decode_access_token(self, token: str, audience: str | None = None) -> TokenClaims:
        try:
            claims = jwt.decode(
                token,
                self._public_key,
                algorithms=[self.settings.jwt_algorithm],
                audience=audience or self.settings.jwt_audience,
                options={"verify_aud": True, "verify_exp": True},
            )
        except JWTError as exc:
            raise TokenError("Invalid or expired access token") from exc

        roles = list((claims.get("realm_access") or {}).get("roles", []) or [])
        permissions = list(claims.get("permissions", []) or [])
        if not claims.get("session_id"):
            raise TokenError("Access token missing session claim")
        return TokenClaims(
            sub=str(claims["sub"]),
            username=claims.get("username", ""),
            jti=str(claims.get("jti", "")),
            session_id=str(claims["session_id"]),
            roles=roles,
            permissions=permissions,
            scope=claims.get("scope", ""),
        )

    # ------------------------------------------------------------ refresh token

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def generate_refresh_token(self) -> tuple[str, str]:
        """Return (plaintext_token, hashed_token). Plaintext is shown once only."""
        plaintext = secrets.token_urlsafe(48)
        return plaintext, self._hash(plaintext)

    @staticmethod
    def hash_refresh_token(plaintext: str) -> str:
        return TokenService._hash(plaintext)

    def expiry_for_refresh(self, now: datetime | None = None) -> datetime:
        now = now or datetime.now(UTC)
        return now + timedelta(seconds=self.settings.jwt_refresh_ttl_seconds)

    # ------------------------------------------------------------ MFA challenge

    def issue_mfa_challenge(self, user: User) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": str(user.id),
            "iss": self.settings.jwt_issuer,
            "aud": "ehos-mfa-challenge",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=self.settings.mfa_challenge_ttl_seconds)).timestamp()),
            "typ": "mfa-challenge",
        }
        return jwt.encode(payload, self._private_key, algorithm=self.settings.jwt_algorithm)

    def verify_mfa_challenge(self, token: str) -> str:
        """Return the user id (sub) if the challenge token is valid."""
        try:
            claims = jwt.decode(
                token,
                self._public_key,
                algorithms=[self.settings.jwt_algorithm],
                audience="ehos-mfa-challenge",
                options={"verify_aud": True, "verify_exp": True},
            )
        except JWTError as exc:
            raise TokenError("Expired or invalid MFA challenge") from exc
        if claims.get("typ") != "mfa-challenge":
            raise TokenError("Invalid MFA challenge type")
        return str(claims["sub"])