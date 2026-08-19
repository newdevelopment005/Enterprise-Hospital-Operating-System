"""Multi-factor authentication (TOTP) service.

Secrets are generated with ``pyotp`` and stored encrypted at rest (Fernet key
derived from a dedicated ``MFA_ENCRYPTION_KEY``, or the configured JWT signing
key when the dedicated key is absent). Enrollment returns a one-time provisioning
URI; the user confirms activation by submitting a valid code before it is enabled.

The encryption key is fail-closed: deriving secrets from an *ephemeral* dev-only
JWT key in a non-development environment is refused, because the dev key
regenerates on every restart and would make all stored MFA secrets undecryptable.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import TYPE_CHECKING

import pyotp
from cryptography.fernet import Fernet

from auth_service.configuration import AuthSettings
from auth_service.dto.schemas import MfaEnrollResponse
from auth_service.entity.models import User, UserMfa

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("authentication-service.mfa")


class MfaService:
    def __init__(self, settings: AuthSettings):
        self.settings = settings
        self._fernet: Fernet | None = None

    def _cipher(self) -> Fernet:
        if self._fernet is not None:
            return self._fernet

        material = self.settings.mfa_encryption_key or self.settings.jwt_private_key_pem
        if not material:
            raise RuntimeError(
                "MFA encryption key is not configured: set MFA_ENCRYPTION_KEY "
                "or inject AUTH_JWT_PRIVATE_KEY"
            )
        if self.settings.mfa_encryption_key is None and (
            not self.settings.jwt_keys_explicit and self.settings.environment != "development"
        ):
            raise RuntimeError(
                "Refusing to derive MFA secrets from an ephemeral dev-only JWT key "
                "in a non-development environment; set MFA_ENCRYPTION_KEY"
            )

        digest = hashlib.sha256(material.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)  # Fernet requires url-safe base64
        self._fernet = Fernet(key)  # noqa: S106 - derived from configured key material
        return self._fernet

    def _encrypt(self, value: str) -> str:
        return self._cipher().encrypt(value.encode("utf-8")).decode("ascii")

    def _decrypt(self, value: str) -> str:
        try:
            return self._cipher().decrypt(value.encode("ascii")).decode("utf-8")
        except Exception:
            log.exception("failed to decrypt MFA secret")
            return ""

    # ------------------------------------------------------------ enrollment

    def generate_secret(self, username: str, issuer: str | None = None) -> MfaEnrollResponse:
        secret = pyotp.random_base32()
        issuer = issuer or self.settings.mfa_issuer
        otpauth = pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)
        return MfaEnrollResponse(secret=secret, otpauth_uri=otpauth, method="TOTP")

    async def enroll(
        self, session: AsyncSession, user: User, secret: str, method: str = "TOTP"
    ) -> UserMfa:
        mfa = UserMfa(
            user_id=user.id,
            method=method,
            secret_encrypted=self._encrypt(secret),
            enabled=False,
        )
        session.add(mfa)
        await session.flush()
        return mfa

    async def confirm(self, session: AsyncSession, user: User, method: str, code: str) -> bool:
        """Activate an enrolled MFA method by validating the first code."""
        mfa = await self.get_method(session, user, method)
        if mfa is None or not mfa.secret_encrypted:
            return False
        secret = self._decrypt(mfa.secret_encrypted)
        if not secret:
            return False
        if not pyotp.TOTP(secret).verify(code, valid_window=self.settings.mfa_window):
            return False
        mfa.enabled = True
        mfa.last_used_at = None
        return True

    # ------------------------------------------------------------ verification

    async def get_method(self, session: AsyncSession, user: User, method: str) -> UserMfa | None:
        from sqlalchemy import select

        result = await session.execute(
            select(UserMfa).where(UserMfa.user_id == user.id, UserMfa.method == method)
        )
        return result.scalar_one_or_none()

    async def enabled_methods(self, session: AsyncSession, user: User) -> list[UserMfa]:
        from sqlalchemy import select

        result = await session.execute(
            select(UserMfa).where(UserMfa.user_id == user.id, UserMfa.enabled.is_(True))
        )
        return list(result.scalars().all())

    async def verify_code(self, session: AsyncSession, user: User, method: str, code: str) -> bool:
        mfa = await self.get_method(session, user, method)
        if mfa is None or not mfa.enabled or not mfa.secret_encrypted:
            return False
        secret = self._decrypt(mfa.secret_encrypted)
        if not secret:
            return False
        return pyotp.TOTP(secret).verify(code, valid_window=self.settings.mfa_window)
