"""Password hashing and password-policy enforcement.

- Passwords are hashed with bcrypt (never stored in plaintext).
- Policies follow AUTHENTICATION.md section 7: min 12 chars, uppercase,
  lowercase, digit, special character, history reuse check, max age.
- Passwords are never logged; validation messages are generic.
"""

from __future__ import annotations

import re
from datetime import UTC

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.configuration import AuthSettings
from auth_service.dto.schemas import PasswordPolicyOut
from auth_service.entity.models import PasswordHistory, User

COMMON_PASSWORDS = {
    "password",
    "password123",
    "12345678",
    "123456789",
    "qwerty123",
    "letmein",
    "admin123",
    "welcome123",
    "P@ssw0rd",
    "changeme",
}


class PasswordService:
    """Hashes, verifies and validates passwords against the configured policy."""

    def __init__(self, settings: AuthSettings):
        self.settings = settings

    # ------------------------------------------------------------ hashing

    def hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

    def verify_password(self, password: str, password_hash: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except ValueError:
            return False

    # ------------------------------------------------------------ policy

    def policy(self) -> PasswordPolicyOut:
        s = self.settings
        return PasswordPolicyOut(
            min_length=s.password_min_length,
            require_upper=s.password_require_upper,
            require_lower=s.password_require_lower,
            require_digit=s.password_require_digit,
            require_special=s.password_require_special,
            history_size=s.password_history_size,
            max_age_days=s.password_max_age_days,
            login_failure_limit=s.login_failure_limit,
            lockout_minutes=s.lockout_minutes,
        )

    def validate(self, password: str) -> list[str]:
        """Return a list of policy violations; empty list means the password is OK."""
        s = self.settings
        violations: list[str] = []
        if len(password) < s.password_min_length:
            violations.append(f"Password must be at least {s.password_min_length} characters")
        if s.password_require_upper and not re.search(r"[A-Z]", password):
            violations.append("Password must contain an uppercase letter")
        if s.password_require_lower and not re.search(r"[a-z]", password):
            violations.append("Password must contain a lowercase letter")
        if s.password_require_digit and not re.search(r"\d", password):
            violations.append("Password must contain a digit")
        if s.password_require_special and not re.search(r"[^A-Za-z0-9]", password):
            violations.append("Password must contain a special character")
        if password.lower() in COMMON_PASSWORDS:
            violations.append("Password is too common")
        if " " in password:
            violations.append("Password must not contain spaces")
        return violations

    async def is_reused(self, session: AsyncSession, user_id, password: str) -> bool:
        """True if the password was used in the last N password changes."""
        history_size = self.settings.password_history_size
        result = await session.execute(
            select(PasswordHistory)
            .where(PasswordHistory.user_id == user_id)
            .order_by(PasswordHistory.created_at.desc())
            .limit(history_size)
        )
        return any(  # noqa: SIM110 - early-exit clarity over generator
            self.verify_password(password, record.password_hash) for record in result.scalars().all()
        )

    async def record_history(self, session: AsyncSession, user: User, password_hash: str) -> None:
        session.add(PasswordHistory(user_id=user.id, password_hash=password_hash))

    def password_expired(self, user: User) -> bool:
        if user.password_changed_at is None:
            return False
        max_age_days = self.settings.password_max_age_days
        from datetime import datetime

        age = (datetime.now(UTC) - user.password_changed_at).days
        return age >= max_age_days
