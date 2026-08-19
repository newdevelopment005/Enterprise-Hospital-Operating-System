"""Core authentication service: register, login, MFA, refresh, sessions, audit.

Every security-relevant action is recorded in ``auth_events`` and published as an
event on ``auth.topic`` so the audit-service can mirror it into the tamper-evident
``audit_db``. Principles applied:

- Passwords verified with timing-safe bcrypt.
- Brute-force protection: lockout after N failures.
- Refresh tokens rotate per use; reuse revokes the whole token family + session.
- Concurrent session limit enforced.
- MFA step-up challenge for enrolled users (or privileged users per policy).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.configuration import AuthSettings
from auth_service.dto.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    MfaChallengeResponse,
    RegisterRequest,
    TokenPairResponse,
)
from auth_service.entity.models import AuthEvent, RefreshToken, User, UserSession
from auth_service.service.mfa_service import MfaService
from auth_service.service.password_service import PasswordService
from auth_service.service.rbac_service import RbacService
from auth_service.service.token_service import TokenError, TokenService

if TYPE_CHECKING:
    from ehos_common.events import KafkaProducer

from ehos_common.events import DomainEvent

log = __import__("logging").getLogger("authentication-service")

AUTH_TOPIC = "auth.topic"


def _as_aware(dt: datetime | None) -> datetime | None:
    """Sqlite returns naive datetimes; Postgres timestamptz aware. Normalize to UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


class AuthServiceError(Exception):
    def __init__(self, error_code: str, message: str, status_code: int = 400):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AuthenticationService:
    def __init__(
        self,
        settings: AuthSettings,
        tokens: TokenService,
        passwords: PasswordService,
        mfa: MfaService,
        rbac: RbacService,
        producer: KafkaProducer | None = None,
    ):
        self.settings = settings
        self.tokens = tokens
        self.passwords = passwords
        self.mfa = mfa
        self.rbac = rbac
        self.producer = producer

    # ------------------------------------------------------------ audit & events

    async def _audit(
        self,
        session: AsyncSession,
        user_id: uuid.UUID | None,
        event_type: str,
        result: str,
        ip: str | None = None,
        user_agent: str | None = None,
        details: dict | None = None,
    ) -> None:
        session.add(
            AuthEvent(
                user_id=user_id,
                event_type=event_type,
                result=result,
                ip_address=ip,
                user_agent=user_agent,
                details=details,
            )
        )

    async def _publish(self, event_type: str, user_id: uuid.UUID | None, details: dict | None) -> None:
        if self.producer is None:
            return
        try:
            await self.producer.publish(
                AUTH_TOPIC,
                DomainEvent(
                    event_type=event_type,
                    source="authentication-service",
                    user_id=str(user_id) if user_id else None,
                    payload=details or {},
                ),
            )
        except Exception:  # noqa: BLE001 - publishing must never break authentication
            log.exception("failed to publish %s", event_type)

    # ------------------------------------------------------------ helpers

    async def _load_user_by_username(self, session: AsyncSession, username: str) -> User | None:
        result = await session.execute(
            select(User).where(
                User.username == username.lower(),
                User.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _make_session(
        self,
        session: AsyncSession,
        user: User,
        refresh_plaintext: str,
        refresh_hash: str,
        client_id: str,
        ip: str | None,
        user_agent: str | None,
        family_id: uuid.UUID,
        parent_hash: str | None,
    ) -> tuple[UserSession, RefreshToken]:
        # concurrent session limit: revoke oldest sessions beyond the max
        existing = await self._active_sessions(session, user)
        if len(existing) >= self.settings.max_sessions_per_user:
            for stale in existing[: len(existing) - self.settings.max_sessions_per_user + 1]:
                stale.revoked = True
                stale.ended_at = datetime.now(UTC)
                stale.status = "REVOKED"

        session_row = UserSession(
            user_id=user.id,
            client_id=client_id,
            ip_address=ip,
            user_agent=user_agent,
            started_at=datetime.now(UTC),
            status="ACTIVE",
        )
        session.add(session_row)
        await session.flush()

        token = RefreshToken(
            user_id=user.id,
            session_id=session_row.id,
            token_hash=refresh_hash,
            family_id=family_id,
            parent_token_hash=parent_hash,
            client_id=client_id,
            ip_address=ip,
            user_agent=user_agent,
            expires_at=self.tokens.expiry_for_refresh(),
            status="ACTIVE",
        )
        session.add(token)
        await session.flush()

        session_row.refresh_token_id = token.id
        user.last_login_at = datetime.now(UTC)
        user.failed_attempts = 0
        user.locked_until = None
        return session_row, token

    async def _active_sessions(self, session: AsyncSession, user: User) -> list[UserSession]:
        result = await session.execute(
            select(UserSession).where(
                UserSession.user_id == user.id,
                UserSession.revoked.is_(False),
                UserSession.status == "ACTIVE",
            ).order_by(UserSession.started_at)
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------ registration

    async def register(self, session: AsyncSession, request: RegisterRequest) -> User:
        violations = self.passwords.validate(request.password.get_secret_value())
        if violations:
            reason = violations[0]
            await self._audit(session, None, "UserRegistration", "failure", details={"reason": reason})
            raise AuthServiceError("WEAK_PASSWORD", reason, status_code=422)

        if await self._load_user_by_username(session, request.username) is not None:
            raise AuthServiceError("USERNAME_TAKEN", "Username is already taken", status_code=409)

        user = User(
            username=request.username.lower(),
            email=request.email.lower(),
            full_name=request.full_name,
            given_name=request.given_name,
            family_name=request.family_name,
            preferred_locale="en",
            enabled=True,
            password_hash=self.passwords.hash_password(request.password.get_secret_value()),
            password_changed_at=datetime.now(UTC),
            must_change_password=True,  # self-service registration forces a change on first login
            status="ACTIVE",
        )
        session.add(user)
        await session.flush()

        # Self-service registration grants the default role only. Client-supplied
        # roles are deliberately ignored to prevent privilege escalation; elevated
        # roles can only be assigned by an administrator.
        default_role = self.settings.register_default_role
        if await self.rbac.get_role(session, default_role) is None:
            await self.rbac.create_role(session, default_role, default_role.replace("_", " ").title(), None)
        await self.rbac.assign_roles(session, user, [default_role])

        await self.passwords.record_history(session, user, user.password_hash)
        await self._audit(session, user.id, "UserRegistration", "success")
        await self._publish("UserRegistered", user.id, {"username": user.username})
        return user

    # ------------------------------------------------------------ login

    async def login(self, session: AsyncSession, request: LoginRequest) -> dict:
        """Returns a TokenPairResponse, or an MFA challenge dict."""
        user = await self._load_user_by_username(session, request.username)
        now = datetime.now(UTC)

        if user is None or user.password_hash is None or not user.enabled:
            # constant-work: still hash a dummy to avoid user enumeration timing
            await self._audit(session, user.id if user else None, "UserLogin", "failure",
                              request.ip_address, request.user_agent, {"reason": "INVALID_CREDENTIALS"})
            self.passwords.verify_password(request.password, "$2b$12$C6UzMDM.H6dHm4mKkx5AeO" + "0" * 11 + "e.7")
            raise AuthServiceError("INVALID_CREDENTIALS", "Invalid username or password", status_code=401)

        if user.locked_until and _as_aware(user.locked_until) > now:
            raise AuthServiceError("ACCOUNT_LOCKED", "Account temporarily locked", status_code=423)

        if not self.passwords.verify_password(request.password, user.password_hash):
            await self._record_failed_login(session, user, request)
            raise AuthServiceError("INVALID_CREDENTIALS", "Invalid username or password", status_code=401)

        # password changed via expiry: challenge to force change? handled in token claim later
        challenge = await self._mfa_decision(session, user)
        if challenge is not None:
            await self._audit(session, user.id, "UserLogin", "success", request.ip_address,
                              request.user_agent, {"mfa_required": True})
            return challenge

        # success, no MFA required
        pair = await self._complete_login(session, user, request)
        pair.change_password_required = user.must_change_password
        await self._audit(session, user.id, "UserLogin", "success", request.ip_address, request.user_agent,
                          {"session_id": str(pair.session_id)})
        await self._publish("UserAuthenticated", user.id, {"username": user.username})
        return pair

    async def _record_failed_login(
        self, session: AsyncSession, user: User, request: LoginRequest
    ) -> None:
        user.failed_attempts += 1
        if user.failed_attempts >= self.settings.login_failure_limit:
            user.locked_until = datetime.now(UTC) + timedelta(minutes=self.settings.lockout_minutes)
            user.failed_attempts = 0
            await self._audit(session, user.id, "AccountLocked", "success", request.ip_address,
                              request.user_agent, {"until": user.locked_until.isoformat()})
        await self._audit(session, user.id, "UserLogin", "failure", request.ip_address,
                          request.user_agent, {"reason": "BAD_PASSWORD"})

    async def _mfa_decision(self, session: AsyncSession, user: User) -> MfaChallengeResponse | None:
        methods = await self.mfa.enabled_methods(session, user)
        if not methods:
            return None
        method = methods[0].method
        challenge = self.tokens.issue_mfa_challenge(user)
        return MfaChallengeResponse(
            method=method,
            challenge_id=challenge,
            message="MFA challenge required",
        )

    async def _complete_login(
        self,
        session: AsyncSession,
        user: User,
        request: LoginRequest,
        challenge: str | None = None,
    ) -> TokenPairResponse:
        plaintext, hashed = self.tokens.generate_refresh_token()
        family = uuid.uuid4()
        session_row, token = await self._make_session(
            session, user, plaintext, hashed, request.client_id,
            request.ip_address, request.user_agent, family, None,
        )
        roles = await self.rbac.role_codes_for_user(session, user)
        permissions = await self.rbac.permissions_for_user(session, user)
        access_token = self.tokens.issue_access_token(user, session_row.id, roles, permissions)
        return TokenPairResponse(
            access_token=access_token,
            refresh_token=plaintext,
            expires_in=self.settings.jwt_access_ttl_seconds,
            refresh_expires_in=self.settings.jwt_refresh_ttl_seconds,
            session_id=str(session_row.id),
            id_token=challenge or None,
        )

    # ------------------------------------------------------------ MFA verify

    async def complete_mfa_login(self, session: AsyncSession, challenge_id: str, code: str,
                                 request: LoginRequest) -> dict:
        sub = self.tokens.verify_mfa_challenge(challenge_id)
        user = await session.get(User, uuid.UUID(sub))
        if user is None or not user.enabled:
            raise AuthServiceError("INVALID_CREDENTIALS", "Invalid MFA challenge", status_code=401)

        if not await self.mfa.verify_code(session, user, "TOTP", code):
            await self._audit(session, user.id, "MfaVerify", "failure", request.ip_address,
                              request.user_agent, {"reason": "BAD_CODE"})
            raise AuthServiceError("INVALID_MFA_CODE", "Invalid one-time code", status_code=401)

        pair = await self._complete_login(session, user, request)
        pair.change_password_required = user.must_change_password
        await self._audit(session, user.id, "MfaVerify", "success", request.ip_address,
                          request.user_agent, {"session_id": str(pair.session_id)})
        await self._publish("UserAuthenticated", user.id, {"username": user.username, "mfa": True})
        return pair

    # ------------------------------------------------------------ refresh

    async def refresh(self, session: AsyncSession, refresh_token: str,
                      client_id: str, ip: str | None, user_agent: str | None) -> TokenPairResponse:
        hashed = self.tokens.hash_refresh_token(refresh_token)
        result = await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hashed)
        )
        token = result.scalar_one_or_none()

        if token is None:
            raise AuthServiceError("INVALID_REFRESH_TOKEN", "Invalid refresh token", status_code=401)

        if token.status == "ROTATED":
            # The previously rotated token is presented again: the rotation
            # response was replayed or the pair was stolen. Revoke the whole
            # family (which also ends any bound session) instead of returning a
            # generic error.
            token.reuse_detected = True
            await self._revoke_family(session, token.family_id)
            await self._audit(session, token.user_id, "TokenReuseDetected", "failure", ip, user_agent)
            raise AuthServiceError("TOKEN_REUSE_DETECTED", "Refresh token reuse detected", status_code=401)

        if token.status != "ACTIVE" or token.revoked_at is not None:
            raise AuthServiceError("INVALID_REFRESH_TOKEN", "Invalid refresh token", status_code=401)

        if _as_aware(token.expires_at) <= datetime.now(UTC):
            token.status = "EXPIRED"
            await self._audit(session, token.user_id, "RefreshToken", "failure", ip, user_agent,
                              {"reason": "EXPIRED"})
            raise AuthServiceError("INVALID_REFRESH_TOKEN", "Refresh token expired", status_code=401)

        if token.reuse_detected:
            # replay of an already-rotated token: revoke entire family + session
            await self._revoke_family(session, token.family_id)
            await self._audit(session, token.user_id, "TokenReuseDetected", "failure", ip, user_agent)
            raise AuthServiceError("TOKEN_REUSE_DETECTED", "Refresh token reuse detected", status_code=401)

        user = await session.get(User, token.user_id)
        if user is None or not user.enabled:
            raise AuthServiceError("INVALID_REFRESH_TOKEN", "User no longer active", status_code=401)

        # rotate: mark current revoked, issue a new token in the same family
        token.status = "ROTATED"
        token.revoked_at = datetime.now(UTC)
        new_plain, new_hash = self.tokens.generate_refresh_token()
        family = token.family_id

        session_row = await session.get(UserSession, token.session_id) if token.session_id else None
        new_token = RefreshToken(
            user_id=user.id,
            session_id=session_row.id if session_row else None,
            token_hash=new_hash,
            family_id=family,
            parent_token_hash=hashed,
            client_id=client_id,
            ip_address=ip,
            user_agent=user_agent,
            expires_at=self.tokens.expiry_for_refresh(),
            status="ACTIVE",
        )
        session.add(new_token)
        await session.flush()
        token.replaced_by = new_token.id
        if session_row:
            session_row.refresh_token_id = new_token.id
            session_row.last_seen_at = datetime.now(UTC)

        roles = await self.rbac.role_codes_for_user(session, user)
        permissions = await self.rbac.permissions_for_user(session, user)
        access_token = self.tokens.issue_access_token(user, new_token.session_id, roles, permissions)

        await self._audit(session, user.id, "RefreshToken", "success", ip, user_agent,
                          {"session_id": str(new_token.session_id)})
        return TokenPairResponse(
            access_token=access_token,
            refresh_token=new_plain,
            expires_in=self.settings.jwt_access_ttl_seconds,
            refresh_expires_in=self.settings.jwt_refresh_ttl_seconds,
            session_id=str(new_token.session_id) if new_token.session_id else "",
        )

    async def _revoke_family(self, session: AsyncSession, family_id: uuid.UUID) -> None:
        result = await session.execute(select(RefreshToken).where(RefreshToken.family_id == family_id))
        for token in result.scalars().all():
            token.status = "REVOKED"
            token.revoked_at = datetime.now(UTC)
        # also revoke any sessions bound to these tokens
        token_ids = [t.id for t in result.scalars()]
        if token_ids:
            s_result = await session.execute(
                select(UserSession).where(UserSession.refresh_token_id.in_(token_ids))
            )
            for srow in s_result.scalars().all():
                srow.revoked = True
                srow.status = "REVOKED"
                srow.ended_at = datetime.now(UTC)

    # ------------------------------------------------------------ sessions

    async def list_sessions(self, session: AsyncSession, user: User, current_session_id) -> list[UserSession]:
        result = await session.execute(
            select(UserSession).where(UserSession.user_id == user.id).order_by(UserSession.started_at.desc())
        )
        rows = list(result.scalars().all())
        for row in rows:
            row.is_current = str(row.id) == str(current_session_id)  # noqa: SLF001
        return rows

    async def revoke_session(self, session: AsyncSession, session_id: uuid.UUID, owner: User) -> bool:
        row = await session.get(UserSession, session_id)
        if row is None or row.user_id != owner.id:
            # Return False (→ 404) so the endpoint neither revokes nor reveals
            # the existence of another user's session.
            return False
        row.revoked = True
        row.status = "REVOKED"
        row.ended_at = datetime.now(UTC)
        if row.refresh_token_id:
            token = await session.get(RefreshToken, row.refresh_token_id)
            if token and token.status == "ACTIVE":
                token.status = "REVOKED"
                token.revoked_at = datetime.now(UTC)
        return True

    async def revoke_all_sessions(self, session: AsyncSession, user: User) -> int:
        rows = await self._active_sessions(session, user)
        for row in rows:
            row.revoked = True
            row.status = "REVOKED"
            row.ended_at = datetime.now(UTC)
            if row.refresh_token_id:
                token = await session.get(RefreshToken, row.refresh_token_id)
                if token and token.status == "ACTIVE":
                    token.status = "REVOKED"
                    token.revoked_at = datetime.now(UTC)
        return len(rows)

    # ------------------------------------------------------------ logout & password

    async def logout(self, session: AsyncSession, refresh_token: str, client_id: str) -> None:
        hashed = self.tokens.hash_refresh_token(refresh_token)
        result = await session.execute(select(RefreshToken).where(RefreshToken.token_hash == hashed))
        token = result.scalar_one_or_none()
        if token is None:
            return
        token.status = "REVOKED"
        token.revoked_at = datetime.now(UTC)
        if token.session_id:
            srow = await session.get(UserSession, token.session_id)
            if srow:
                srow.revoked = True
                srow.status = "ENDED"
                srow.ended_at = datetime.now(UTC)
        await self._audit(session, token.user_id, "UserLogout", "success", details={"client_id": client_id})

    async def change_password(self, session: AsyncSession, user: User,
                              request: ChangePasswordRequest, ip: str | None) -> None:
        if not self.passwords.verify_password(request.current_password, user.password_hash or ""):
            await self._audit(session, user.id, "PasswordChange", "failure", ip, details={"reason": "BAD_CURRENT"})
            raise AuthServiceError("INVALID_CURRENT_PASSWORD", "Current password is incorrect", status_code=401)

        new_password = request.new_password.get_secret_value()
        violations = self.passwords.validate(new_password)
        if violations:
            raise AuthServiceError("WEAK_PASSWORD", violations[0], status_code=422)
        if await self.passwords.is_reused(session, user.id, new_password):
            raise AuthServiceError("PASSWORD_REUSED", "Password was used recently; choose a new one", status_code=422)

        new_hash = self.passwords.hash_password(new_password)
        user.password_hash = new_hash
        user.password_changed_at = datetime.now(UTC)
        user.must_change_password = False
        user.version += 1
        await self.passwords.record_history(session, user, new_hash)
        await self._audit(session, user.id, "PasswordChange", "success", ip)
        await self._publish("PasswordChanged", user.id, {})

    # ------------------------------------------------------------ introspection

    async def introspect_access_token(self, session: AsyncSession, token: str) -> dict:
        try:
            claims = self.tokens.decode_access_token(token)
        except TokenError:
            return {"active": False}
        return {
            "active": True,
            "sub": claims.sub,
            "username": claims.username,
            "exp": None,  # kept minimal; full claims returned in /me
            "iat": None,
            "jti": claims.jti,
            "client_id": "ehos-api",
            "scope": claims.scope,
        }