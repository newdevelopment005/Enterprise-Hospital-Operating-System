"""Regression tests for security state surviving the request error path.

``get_session`` commits pending security state (failed-login counters, lockouts,
refresh-token family revocations) even when the handler answers with an error.
Without that, brute-force lockout and token-reuse family revocation would be
silently rolled back and never take effect.
"""

import contextlib
import types
import uuid

import pytest
from ehos_common.db import Database
from sqlalchemy import select

from auth_service.api.routes import get_session
from auth_service.dto.schemas import LoginRequest, RegisterRequest
from auth_service.entity.models import Base, User, UserSession
from auth_service.service.auth_service import AuthServiceError

VALID = "Str0ng!Passw0rd"


def register(username: str) -> RegisterRequest:
    return RegisterRequest(
        username=username,
        email=f"{username}@example.com",
        password=VALID,
        full_name=username,
    )


async def _request(db: Database):
    return types.SimpleNamespace(app=types.SimpleNamespace(state=types.SimpleNamespace(database=db)))


async def test_lockout_persists_through_error_path(auth, tmp_path):
    """Failed logins raised through the request dependency must lock the account."""
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}")
    await db.init_models(Base)

    # registration request cycle
    request = await _request(db)
    gen = get_session(request)
    s = await gen.__anext__()
    try:
        await auth.register(s, register("drhealy"))
    finally:
        with contextlib.suppress(StopAsyncIteration):
            await gen.asend(None)  # commit on success

    # each failed login is its own request cycle; the handler raises, and the
    # dependency must persist the counter/lockout before re-raising
    for _ in range(auth.settings.login_failure_limit):
        request = await _request(db)
        gen = get_session(request)
        s = await gen.__anext__()
        try:
            with pytest.raises(AuthServiceError):
                await auth.login(s, LoginRequest(username="drhealy", password="WrongPass!123"))
        finally:
            with pytest.raises(AuthServiceError):
                await gen.athrow(AuthServiceError("INVALID_CREDENTIALS", "bad", status_code=401))
    # a subsequent correct login must now be rejected as locked
    request = await _request(db)
    gen = get_session(request)
    s = await gen.__anext__()
    try:
        with pytest.raises(AuthServiceError) as exc:
            await auth.login(s, LoginRequest(username="drhealy", password=VALID))
        assert exc.value.error_code == "ACCOUNT_LOCKED"
    finally:
        with pytest.raises(AuthServiceError):
            await gen.athrow(exc.value)

    await db.dispose()


async def test_session_revocation_requires_ownership(session, auth):
    await auth.register(session, register("drhealy"))
    await auth.register(session, register("nursej"))
    await session.flush()

    pair_a = await auth.login(session, LoginRequest(username="drhealy", password=VALID))
    pair_b = await auth.login(session, LoginRequest(username="nursej", password=VALID))
    await session.flush()

    user_a = (await session.execute(select(User).where(User.username == "drhealy"))).scalar_one()
    user_b = (await session.execute(select(User).where(User.username == "nursej"))).scalar_one()
    assert user_b is not None

    sid_a = uuid.UUID(pair_a.session_id)
    sid_b = uuid.UUID(pair_b.session_id)

    # user A must not be able to revoke user B's session
    assert await auth.revoke_session(session, sid_b, user_a) is False

    row_b = await session.get(UserSession, sid_b)
    assert row_b is not None and row_b.revoked is False

    # owner can still revoke their own session
    assert await auth.revoke_session(session, sid_a, user_a) is True
    row_a = await session.get(UserSession, sid_a)
    assert row_a is not None and row_a.revoked is True
