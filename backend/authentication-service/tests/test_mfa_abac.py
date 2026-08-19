"""Tests for TOTP MFA and ABAC policy evaluation."""

import pyotp
import pytest
from sqlalchemy import select

from auth_service.dto.schemas import AbacCheckRequest, LoginRequest, RegisterRequest
from auth_service.entity.models import User
from auth_service.service.abac_service import AbacService
from auth_service.service.auth_service import AuthServiceError

VALID = "Str0ng!Passw0rd"

REGISTER = RegisterRequest(
    username="nursepaul",
    email="paul@example.com",
    password=VALID,
    full_name="Nurse Paul",
)


async def _register_and_login(session, auth) -> dict:
    await auth.register(session, REGISTER)
    await session.flush()
    return await auth.login(session, LoginRequest(username="nursepaul", password=VALID))


async def test_mfa_enroll_confirm_and_login(session, auth):
    result = await _register_and_login(session, auth)
    assert result.mfa_required is False


    user = (await session.execute(select(User).where(User.username == "nursepaul"))).scalar_one()

    secret = auth.mfa.generate_secret(user.username)
    await auth.mfa.enroll(session, user, secret.secret, "TOTP")
    await session.flush()

    code = pyotp.TOTP(secret.secret).now()
    assert await auth.mfa.confirm(session, user, "TOTP", code) is True

    # login now returns an MFA challenge
    result = await auth.login(session, LoginRequest(username="nursepaul", password=VALID))
    assert result.mfa_required is True
    assert result.challenge_id

    # completing the challenge issues a token pair
    pair = await auth.complete_mfa_login(session, result.challenge_id, code, LoginRequest(
        username="nursepaul", password=VALID,
    ))
    assert pair.access_token
    assert pair.session_id


async def test_mfa_wrong_code(session, auth):
    result = await _register_and_login(session, auth)

    user = (await session.execute(select(User).where(User.username == "nursepaul"))).scalar_one()
    secret = auth.mfa.generate_secret(user.username)
    await auth.mfa.enroll(session, user, secret.secret, "TOTP")
    await session.flush()
    await auth.mfa.confirm(session, user, "TOTP", pyotp.TOTP(secret.secret).now())

    result = await auth.login(session, LoginRequest(username="nursepaul", password=VALID))
    with pytest.raises(AuthServiceError) as exc:
        await auth.complete_mfa_login(
            session, result.challenge_id, "000000",
            LoginRequest(username="nursepaul", password=VALID),
        )
    assert exc.value.error_code == "INVALID_MFA_CODE"


async def test_mfa_secret_encrypted_at_rest(session, auth):
    await _register_and_login(session, auth)
    from auth_service.entity.models import UserMfa

    user = (await session.execute(select(User).where(User.username == "nursepaul"))).scalar_one()
    secret = auth.mfa.generate_secret(user.username)
    await auth.mfa.enroll(session, user, secret.secret, "TOTP")
    await session.flush()

    stored = (await session.execute(
        select(UserMfa).where(UserMfa.user_id == user.id)
    )).scalar_one()
    assert stored.secret_encrypted is not None
    assert secret.secret not in stored.secret_encrypted  # never plaintext at rest


async def test_abac_allow_and_default_deny(session, auth):
    svc = AbacService()
    await svc.create_policy(
        session,
        code="icu-nurse-read",
        resource="patient.record",
        action="read",
        effect="allow",
        conditions={
            "department": {"==": "icu"},
            "role": {"in": ["nurse", "doctor"]},
            "clearance": {"gte": 2},
        },
        priority=10,
        description="ICU staff may read patient records",
    )
    await session.flush()

    decision = await svc.evaluate(
        session,
        AbacCheckRequest(
            resource="patient.record",
            action="read",
            attributes={"department": "icu", "role": "nurse", "clearance": 3},
        ),
    )
    assert decision.effect == "allow"

    blocked = await svc.evaluate(
        session,
        AbacCheckRequest(
            resource="patient.record",
            action="read",
            attributes={"department": "icu", "role": "nurse", "clearance": 1},
        ),
    )
    assert blocked.effect == "deny"

    # no matching policy -> default deny (zero trust)
    denied = await svc.evaluate(
        session,
        AbacCheckRequest(resource="physical.therapy", action="read", attributes={}),
    )
    assert denied.effect == "deny"


async def test_abac_deny_overrides_allow(session, auth):
    svc = AbacService()
    await svc.create_policy(session, "allow-all", "ehr", "read", "allow", {}, 1, None)
    await svc.create_policy(
        session, "deny-icu", "ehr", "read", "deny",
        {"department": {"==": "icu"}}, 100, None,
    )
    await session.flush()

    decision = await svc.evaluate(
        session,
        AbacCheckRequest(resource="ehr", action="read", attributes={"department": "icu"}),
    )
    assert decision.effect == "deny"