"""Pydantic request/response schemas for the authentication-service."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr

# ---------------------------------------------------------------- auth core

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)
    client_id: str = "ehos-api"
    ip_address: str | None = None
    user_agent: str | None = None


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=255)
    email: EmailStr
    password: SecretStr
    full_name: str | None = Field(default=None, max_length=255)
    given_name: str | None = Field(default=None, max_length=255)
    family_name: str | None = Field(default=None, max_length=255)
    # Accepted for backward compatibility but IGNORED by the service: self-service
    # registration always assigns the default role, never client-supplied roles
    # (privilege-escalation hardening). Elevated roles require an administrator.
    roles: list[str] = Field(default_factory=list, exclude=True)


class MfaChallengeRequest(BaseModel):
    """Presented when a login requires step-up MFA."""

    challenge_id: str
    method: str
    required: bool = True


class MfaChallengeResponse(BaseModel):
    """Returned by POST /auth/login when the user has MFA enabled."""

    mfa_required: Literal[True] = True
    method: str
    challenge_id: str
    message: str
    change_password_required: bool = False


class MfaVerifyRequest(BaseModel):
    challenge_id: str
    code: str = Field(min_length=4, max_length=10)
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)
    client_id: str = "ehos-api"
    ip_address: str | None = None
    user_agent: str | None = None


class MfaEnrollRequest(BaseModel):
    method: str = Field(default="TOTP", pattern="^(TOTP|SMS|EMAIL|WEBAUTHN)$")


class MfaEnrollResponse(BaseModel):
    secret: str
    otpauth_uri: str
    method: str
    qr_data_url: bool = False


class MfaConfirmRequest(BaseModel):
    code: str = Field(min_length=4, max_length=10)


class TokenPairResponse(BaseModel):
    mfa_required: Literal[False] = False
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"  # noqa: S105 - literal constant, not a secret
    expires_in: int
    refresh_expires_in: int
    session_id: str
    not_before_policy: int = 0
    scope: str = "openid profile email"
    id_token: str | None = None
    change_password_required: bool = False


LoginResponse = Annotated[TokenPairResponse | MfaChallengeResponse, Field(discriminator="mfa_required")]


class RefreshRequest(BaseModel):
    refresh_token: str
    client_id: str = "ehos-api"
    ip_address: str | None = None
    user_agent: str | None = None


class LogoutRequest(BaseModel):
    refresh_token: str
    client_id: str = "ehos-api"


class TokenIntrospectionRequest(BaseModel):
    token: str


class TokenIntrospectionResponse(BaseModel):
    active: bool
    sub: str | None = None
    username: str | None = None
    exp: int | None = None
    iat: int | None = None
    jti: str | None = None
    client_id: str | None = None
    scope: str | None = None


# ---------------------------------------------------------------- users & me

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: str
    email_verified: bool
    full_name: str | None
    given_name: str | None
    family_name: str | None
    enabled: bool
    must_change_password: bool
    attributes: dict | None
    created_at: datetime
    last_login_at: datetime | None


class MeResponse(UserOut):
    roles: list[str]
    permissions: list[str]
    mfa_enabled: bool


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: SecretStr


class AdminResetPasswordRequest(BaseModel):
    new_password: SecretStr


# ---------------------------------------------------------------- sessions

class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    client_id: str
    ip_address: str | None
    user_agent: str | None
    started_at: datetime
    last_seen_at: datetime | None
    ended_at: datetime | None
    revoked: bool
    current: bool = False


# ---------------------------------------------------------------- RBAC

class RoleIn(BaseModel):
    code: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=500)


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    description: str | None
    status: str


class PermissionIn(BaseModel):
    code: str = Field(min_length=2, max_length=150)
    resource: str = Field(min_length=1, max_length=150)
    action: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=500)


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    resource: str
    action: str
    description: str | None
    status: str


class AssignRoleRequest(BaseModel):
    role_codes: list[str] = Field(default_factory=list)


class GrantPermissionRequest(BaseModel):
    permission_codes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- ABAC

class AbacPolicyIn(BaseModel):
    code: str = Field(min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    resource: str = Field(min_length=1, max_length=150)
    action: str = Field(min_length=1, max_length=50)
    effect: str = Field(pattern="^(allow|deny)$")
    conditions: dict = Field(default_factory=dict)
    priority: int = 0
    enabled: bool = True


class AbacPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    description: str | None
    resource: str
    action: str
    effect: str
    conditions: dict
    priority: int
    enabled: bool
    status: str


class AbacCheckRequest(BaseModel):
    principal_id: str | None = None
    principal_roles: list[str] = Field(default_factory=list)
    resource: str = Field(min_length=1, max_length=150)
    action: str = Field(min_length=1, max_length=50)
    attributes: dict = Field(default_factory=dict)  # subject attributes


class AbacEffect(BaseModel):
    policy_code: str
    effect: str


class AbacCheckResponse(BaseModel):
    decision: str  # "allow" | "deny"
    matched: list[AbacEffect] = Field(default_factory=list)


# ---------------------------------------------------------------- policy & meta

class PasswordPolicyOut(BaseModel):
    min_length: int
    require_upper: bool
    require_lower: bool
    require_digit: bool
    require_special: bool
    history_size: int
    max_age_days: int
    login_failure_limit: int
    lockout_minutes: int


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str | None
    event_type: str
    result: str
    ip_address: str | None
    user_agent: str | None
    details: dict | None
    created_at: datetime


class WellKnownResponse(BaseModel):
    """OIDC discovery document (SSO-ready)."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    end_session_endpoint: str
    jwks_uri: str
    response_types_supported: list[str]
    grant_types_supported: list[str]
    subject_types_supported: list[str]
    id_token_signing_alg_values_supported: list[str]
    scopes_supported: list[str]
    claims_supported: list[str]