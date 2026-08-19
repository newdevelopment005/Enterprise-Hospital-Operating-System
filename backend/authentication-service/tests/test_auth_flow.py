"""Tests for password policy, token service, and authentication flow."""

import pytest

from auth_service.dto.schemas import LoginRequest, RegisterRequest
from auth_service.service.auth_service import AuthServiceError


def build_register(password: str) -> RegisterRequest:
    return RegisterRequest(
        username="drhealy",
        email="healy@example.com",
        password=password,
        full_name="Dr. Healy",
        roles=["doctor"],
    )


VALID = "Str0ng!Passw0rd"


async def test_register_and_login(session, auth, passwords):
    await auth.register(session, build_register(VALID))
    await session.flush()
    token = await auth.login(
        session,
        LoginRequest(username="DrHealy", password=VALID),  # case-insensitive username
    )
    assert token.refresh_token
    assert token.session_id
    assert token.mfa_required is False

    assert auth.tokens.decode_access_token(token.access_token).username == "drhealy"


async def test_register_rejects_weak_password(session, auth):
    with pytest.raises(AuthServiceError) as exc:
        await auth.register(session, build_register("weak"))
    assert exc.value.error_code == "WEAK_PASSWORD"


async def test_login_wrong_password(session, auth):
    await auth.register(session, build_register(VALID))
    await session.flush()
    with pytest.raises(AuthServiceError) as exc:
        await auth.login(session, LoginRequest(username="drhealy", password="WrongPass!123"))
    assert exc.value.status_code == 401
    assert exc.value.error_code == "INVALID_CREDENTIALS"


async def test_login_unknown_user(session, auth):
    with pytest.raises(AuthServiceError) as exc:
        await auth.login(session, LoginRequest(username="ghost", password="Whatever!123"))
    assert exc.value.error_code == "INVALID_CREDENTIALS"


async def test_account_lockout(session, auth):
    await auth.register(session, build_register(VALID))
    await session.flush()
    for _ in range(auth.settings.login_failure_limit):
        with pytest.raises(AuthServiceError):
            await auth.login(session, LoginRequest(username="drhealy", password="WrongPass!123"))
    with pytest.raises(AuthServiceError) as exc:
        await auth.login(session, LoginRequest(username="drhealy", password=VALID))
    assert exc.value.error_code == "ACCOUNT_LOCKED"


async def test_refresh_rotation_and_reuse_detection(session, auth):
    await auth.register(session, build_register(VALID))
    await session.flush()
    pair = await auth.login(session, LoginRequest(username="drhealy", password=VALID))

    new_pair = await auth.refresh(session, pair.refresh_token, "ehos-api", None, None)
    assert new_pair.refresh_token != pair.refresh_token

    # replaying the old (rotated) token must trigger family-wide revocation
    with pytest.raises(AuthServiceError) as exc:
        await auth.refresh(session, pair.refresh_token, "ehos-api", None, None)
    assert exc.value.error_code == "TOKEN_REUSE_DETECTED"

    # the whole family is now revoked, so the sibling (just-issued) token is dead too
    with pytest.raises(AuthServiceError) as exc:
        await auth.refresh(session, new_pair.refresh_token, "ehos-api", None, None)
    assert exc.value.error_code != "TOKEN_REUSE_DETECTED"


async def test_passwords_service_policy(session, auth, passwords):
    assert passwords.verify_password(VALID, passwords.hash_password(VALID))
    assert passwords.validate("short") != []
    assert passwords.validate(VALID) == []
    policy = passwords.policy()
    assert policy.min_length == auth.settings.password_min_length


async def test_rbac_assignment_and_permissions(session, auth, rbac):
    # Regression test for the privilege-escalation fix: client-supplied roles in
    # RegisterRequest are IGNORED; registration always assigns the default role.
    await auth.register(session, build_register(VALID))
    await session.flush()
    from sqlalchemy import select

    from auth_service.entity.models import User

    user = (await session.execute(select(User).where(User.username == "drhealy"))).scalar_one()

    roles = await rbac.role_codes_for_user(session, user)
    assert auth.settings.register_default_role in roles
    assert "doctor" not in roles  # caller-supplied "doctor" role must not be granted

    # Privileged roles are granted only through the (administrator-gated) RBAC API.
    await rbac.assign_roles(session, user, ["doctor"])
    assert "doctor" in (await rbac.role_codes_for_user(session, user))

    await rbac.create_permission(session, "ehr.read", "ehr.record", "read", None)
    doctor = await rbac.get_role(session, "doctor")
    await rbac.grant_permissions(session, doctor, ["ehr.read"])

    perms = await rbac.permissions_for_user(session, user)
    assert "ehr.read" in perms