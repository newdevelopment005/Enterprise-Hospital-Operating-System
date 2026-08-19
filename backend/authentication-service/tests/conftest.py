"""Shared fixtures: in-memory async SQLite, real RSA keys, and the service graph."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from auth_service.configuration import AuthSettings, _ensure_keys
from auth_service.entity.models import Base
from auth_service.service.auth_service import AuthenticationService
from auth_service.service.mfa_service import MfaService
from auth_service.service.password_service import PasswordService
from auth_service.service.rbac_service import RbacService
from auth_service.service.token_service import TokenService


@pytest.fixture
def settings() -> AuthSettings:
    s = AuthSettings()
    _ensure_keys(s)
    assert s.jwt_private_key_pem and s.jwt_public_key_pem
    return s


@pytest.fixture
def tokens(settings: AuthSettings) -> TokenService:
    return TokenService(settings)


@pytest.fixture
def passwords(settings: AuthSettings) -> PasswordService:
    return PasswordService(settings)


@pytest.fixture
def mfa(settings: AuthSettings) -> MfaService:
    return MfaService(settings)


@pytest.fixture
def rbac() -> RbacService:
    return RbacService()


@pytest.fixture
def auth(settings: AuthSettings, tokens: TokenService, passwords: PasswordService,
         mfa: MfaService, rbac: RbacService) -> AuthenticationService:
    return AuthenticationService(settings, tokens, passwords, mfa, rbac)


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()