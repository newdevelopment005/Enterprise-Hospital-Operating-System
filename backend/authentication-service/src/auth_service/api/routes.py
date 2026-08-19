"""REST API for the authentication-service.

All endpoints live under ``/api/v1/auth`` and return the standard EHOS envelope
(success / error with ``errorCode``). Unauthenticated flows: register, login,
MFA verify, refresh, logout, token introspection, password policy and OIDC
discovery. Everything else requires a valid OAuth2 bearer access token.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from ehos_common.api import ForbiddenError, NotFoundError, ServiceError, UnauthorizedError, success_response
from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.configuration import AuthSettings
from auth_service.dto.schemas import (
    AbacCheckRequest,
    AbacPolicyIn,
    AssignRoleRequest,
    ChangePasswordRequest,
    GrantPermissionRequest,
    LoginRequest,
    MeResponse,
    MfaConfirmRequest,
    MfaEnrollRequest,
    MfaVerifyRequest,
    PermissionIn,
    RefreshRequest,
    RegisterRequest,
    RoleIn,
    SessionOut,
    TokenIntrospectionRequest,
)
from auth_service.entity.models import User
from auth_service.service.auth_service import AuthenticationService
from auth_service.service.rbac_service import RbacService
from auth_service.service.token_service import TokenError, TokenService

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
bearer_scheme = HTTPBearer(auto_error=False)


# ------------------------------------------------------------------ dependencies

async def get_session(request: Request) -> AsyncSession:
    async with request.app.state.database.session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            # Persist security-relevant state even when the handler answers with
            # an error: failed-login counters, lockouts and refresh-token family
            # revocations would otherwise be rolled back, making brute-force
            # protection and token-reuse detection ineffective.
            if session.new or session.dirty or session.deleted:
                try:
                    await session.commit()
                except Exception:
                    await session.rollback()
            else:
                await session.rollback()
            raise


def get_auth_service(request: Request) -> AuthenticationService:
    return request.app.state.auth_service


def get_token_service(request: Request) -> TokenService:
    return request.app.state.token_service


def get_rbac_service(request: Request) -> RbacService:
    return request.app.state.rbac_service


def get_settings(request: Request) -> AuthSettings:
    return request.app.state.settings


AuthSvc = Annotated[AuthenticationService, Depends(get_auth_service)]
TokenSvc = Annotated[TokenService, Depends(get_token_service)]
RbacSvc = Annotated[RbacService, Depends(get_rbac_service)]
Settings = Annotated[AuthSettings, Depends(get_settings)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: AsyncSession = Depends(get_session),
    tokens: TokenSvc = ...,
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError("Authentication required")
    try:
        claims = tokens.decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise UnauthorizedError(str(exc)) from exc
    user = await session.get(User, claims.sub)
    if user is None or not user.enabled:
        raise UnauthorizedError("Account is disabled or unknown")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_admin_user(
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
    rbac: RbacSvc = ...,
) -> User:
    """Require the caller to hold the ``administrator`` role."""
    roles = await rbac.role_codes_for_user(session, user)
    if "administrator" not in roles:
        raise ForbiddenError("Administrator role required")
    return user


AdminUser = Annotated[User, Depends(get_admin_user)]


# ------------------------------------------------------------------ public (no auth)

@router.post("/register")
async def register(
    data: RegisterRequest,
    session: AsyncSession = Depends(get_session),
    svc: AuthSvc = ...,
) -> dict:
    user = await svc.register(session, data)
    return success_response(serialize_user(user))


@router.post("/login")
async def login(data: LoginRequest, session: AsyncSession = Depends(get_session), svc: AuthSvc = ...) -> dict:
    """Authenticate; returns a token pair unless the user has MFA enrolled."""
    result = await svc.login(session, data)
    return success_response(result)


@router.post("/mfa/verify")
async def mfa_verify(data: MfaVerifyRequest, session: AsyncSession = Depends(get_session), svc: AuthSvc = ...) -> dict:
    login = LoginRequest(
        username=data.username,
        password=data.password,
        client_id=data.client_id,
        ip_address=data.ip_address,
        user_agent=data.user_agent,
    )
    pair = await svc.complete_mfa_login(session, data.challenge_id, data.code, login)
    return success_response(pair)


@router.post("/refresh")
async def refresh(data: RefreshRequest, session: AsyncSession = Depends(get_session), svc: AuthSvc = ...) -> dict:
    pair = await svc.refresh(session, data.refresh_token, data.client_id, data.ip_address, data.user_agent)
    return success_response(pair)


@router.post("/logout")
async def logout(data: RefreshRequest, session: AsyncSession = Depends(get_session), svc: AuthSvc = ...) -> dict:
    await svc.logout(session, data.refresh_token, data.client_id)
    return success_response({"revoked": True})


@router.post("/introspect")
async def introspect(
    data: TokenIntrospectionRequest, session: AsyncSession = Depends(get_session), svc: AuthSvc = ...
) -> dict:
    return success_response(await svc.introspect_access_token(session, data.token))


@router.get("/policy/password")
async def get_password_policy(svc: AuthSvc = ...) -> dict:
    return success_response(svc.passwords.policy())


@router.get("/.well-known/openid-configuration")
async def oidc_discovery(settings: Settings = ...) -> dict:
    """OIDC discovery document (SSO-ready integration point)."""
    base = settings.jwt_issuer
    return success_response(
        {
            "issuer": base,
            "authorization_endpoint": f"{base}/protocol/openid-connect/auth",
            "token_endpoint": f"{base}/protocol/openid-connect/token",
            "end_session_endpoint": f"{base}/protocol/openid-connect/logout",
            "jwks_uri": f"{base}/protocol/openid-connect/certs",
            "response_types_supported": ["code", "token", "id_token"],
            "grant_types_supported": ["authorization_code", "implicit", "password", "refresh_token"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": [settings.jwt_algorithm],
            "scopes_supported": ["openid", "profile", "email"],
            "claims_supported": ["sub", "username", "email", "roles", "permissions"],
        }
    )


# ------------------------------------------------------------------ authenticated

@router.get("/me")
async def me(
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
    svc: AuthSvc = ...,
) -> dict:
    roles = await svc.rbac.role_codes_for_user(session, user)
    permissions = await svc.rbac.permissions_for_user(session, user)
    mfa_enabled = len(await svc.mfa.enabled_methods(session, user)) > 0
    return success_response(
        MeResponse(
            **serialize_user(user),
            roles=roles,
            permissions=permissions,
            mfa_enabled=mfa_enabled,
        )
    )


@router.put("/me/password")
async def change_password(
    data: ChangePasswordRequest,
    user: CurrentUser,
    request: Request,
    session: AsyncSession = Depends(get_session),
    svc: AuthSvc = ...,
) -> dict:
    ip = request.client.host if request.client else None
    await svc.change_password(session, user, data, ip)
    return success_response({"changed": True})


@router.get("/sessions")
async def list_sessions(
    user: CurrentUser,
    request: Request,
    session: AsyncSession = Depends(get_session),
    svc: AuthSvc = ...,
) -> dict:
    current_session_id = _session_id_from_header(request, svc.tokens)
    rows = await svc.list_sessions(session, user, current_session_id)
    return success_response([session_to_out(row, str(row.id) == current_session_id) for row in rows])


@router.delete("/sessions")
async def revoke_all_sessions(
    user: CurrentUser, session: AsyncSession = Depends(get_session), svc: AuthSvc = ...
) -> dict:
    count = await svc.revoke_all_sessions(session, user)
    return success_response({"revoked": count})


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
    svc: AuthSvc = ...,
) -> dict:
    ok = await svc.revoke_session(session, _as_uuid(session_id), user)
    if not ok:
        raise NotFoundError("Session not found")
    return success_response({"revoked": True})


@router.get("/mfa")
async def list_mfa(user: CurrentUser, session: AsyncSession = Depends(get_session), svc: AuthSvc = ...) -> dict:
    methods = await svc.mfa.enabled_methods(session, user)
    out = [{"method": m.method, "enabled": m.enabled, "last_used_at": m.last_used_at} for m in methods]
    return success_response(out)


@router.post("/mfa/enroll")
async def mfa_enroll(
    data: MfaEnrollRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
    svc: AuthSvc = ...,
) -> dict:
    base = svc.mfa.generate_secret(user.username)
    await svc.mfa.enroll(session, user, base.secret, data.method)
    return success_response(base)


@router.post("/mfa/confirm")
async def mfa_confirm(
    data: MfaConfirmRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
    svc: AuthSvc = ...,
) -> dict:
    ok = await svc.mfa.confirm(session, user, "TOTP", data.code)
    if not ok:
        raise ServiceError("MFA_CONFIRM_FAILED", "Confirmation code rejected", status_code=400)
    return success_response({"enabled": True})


@router.get("/roles")
async def list_roles(user: CurrentUser, session: AsyncSession = Depends(get_session), rbac: RbacSvc = ...) -> dict:
    return success_response(await rbac.list_roles(session))


@router.post("/roles")
async def create_role(
    data: RoleIn, user: AdminUser, session: AsyncSession = Depends(get_session), rbac: RbacSvc = ...
) -> dict:
    role = await rbac.create_role(session, data.code, data.name, data.description)
    return success_response(role)


@router.get("/permissions")
async def list_permissions(
    user: CurrentUser, session: AsyncSession = Depends(get_session), rbac: RbacSvc = ...
) -> dict:
    return success_response(await rbac.list_permissions(session))


@router.post("/permissions")
async def create_permission(
    data: PermissionIn, user: AdminUser, session: AsyncSession = Depends(get_session), rbac: RbacSvc = ...
) -> dict:
    perm = await rbac.create_permission(session, data.code, data.resource, data.action, data.description)
    return success_response(perm)


@router.get("/users/{user_id}/roles")
async def user_roles(
    user_id: str, user: CurrentUser, session: AsyncSession = Depends(get_session), rbac: RbacSvc = ...
) -> dict:
    target = await session.get(User, user_id)
    if target is None:
        raise NotFoundError("User not found")
    return success_response(await rbac.roles_for_user(session, target))


@router.post("/users/{user_id}/roles")
async def assign_roles(
    user_id: str,
    data: AssignRoleRequest,
    user: AdminUser,
    session: AsyncSession = Depends(get_session),
    rbac: RbacSvc = ...,
) -> dict:
    target = await session.get(User, user_id)
    if target is None:
        raise NotFoundError("User not found")
    await rbac.assign_roles(session, target, data.role_codes)
    return success_response(await rbac.roles_for_user(session, target))


@router.post("/roles/{role_code}/permissions")
async def grant_permissions(
    role_code: str,
    data: GrantPermissionRequest,
    user: AdminUser,
    session: AsyncSession = Depends(get_session),
    rbac: RbacSvc = ...,
) -> dict:

    role = await rbac.get_role(session, role_code)
    if role is None:
        raise NotFoundError("Role not found")
    await rbac.grant_permissions(session, role, data.permission_codes)
    return success_response({"granted": data.permission_codes})


@router.get("/abac/policies")
async def list_abac_policies(
    user: AdminUser, session: AsyncSession = Depends(get_session), svc: AuthSvc = ...
) -> dict:
    from auth_service.service.abac_service import AbacService

    return success_response(await AbacService().list_policies(session))


@router.post("/abac/policies")
async def create_abac_policy(
    data: AbacPolicyIn, user: AdminUser, session: AsyncSession = Depends(get_session), svc: AuthSvc = ...
) -> dict:
    from auth_service.service.abac_service import AbacService

    policy = await AbacService().create_policy(
        session, data.code, data.resource, data.action, data.effect, data.conditions, data.priority,
        data.description, data.enabled,
    )
    return success_response(policy)


@router.post("/abac/check")
async def abac_check(
    data: AbacCheckRequest, user: CurrentUser, session: AsyncSession = Depends(get_session), svc: AuthSvc = ...
) -> dict:
    from auth_service.service.abac_service import AbacService

    decision = await AbacService().evaluate(session, data)
    return success_response({"decision": decision.effect, "matched": decision.matched})


@router.get("/users")
async def list_users(
    user: AdminUser, session: AsyncSession = Depends(get_session), svc: AuthSvc = ...
) -> dict:
    result = await session.execute(
        select(User).where(User.deleted_at.is_(None)).order_by(User.username).limit(500)
    )
    return success_response([serialize_user(u) for u in result.scalars().all()])


@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: str, user: AdminUser, session: AsyncSession = Depends(get_session), svc: AuthSvc = ...
) -> dict:
    target = await session.get(User, user_id)
    if target is None:
        raise NotFoundError("User not found")
    target.enabled = False
    target.status = "DISABLED"
    await svc.revoke_all_sessions(session, target)
    return success_response({"disabled": True})


# ------------------------------------------------------------------ helpers

def _as_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise NotFoundError("Invalid identifier") from exc


def _session_id_from_header(request: Request, tokens: TokenService) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            return tokens.decode_access_token(auth.split(" ", 1)[1]).session_id
        except TokenError:
            return ""
    return ""


def serialize_user(user: User) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "email_verified": user.email_verified,
        "full_name": user.full_name,
        "given_name": user.given_name,
        "family_name": user.family_name,
        "enabled": user.enabled,
        "must_change_password": user.must_change_password,
        "attributes": user.attributes,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
    }


def session_to_out(row, current: bool) -> SessionOut:
    return SessionOut(
        id=str(row.id),
        client_id=row.client_id,
        ip_address=row.ip_address,
        user_agent=row.user_agent,
        started_at=row.started_at,
        last_seen_at=row.last_seen_at,
        ended_at=row.ended_at,
        revoked=row.revoked,
        current=current,
    )