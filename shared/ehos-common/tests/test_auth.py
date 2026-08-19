"""Tests for the shared FastAPI auth dependency."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from ehos_common.auth import AuthDeps, build_auth_deps  # noqa: E402
from ehos_common.config import ServiceSettings  # noqa: E402


class _FakeVerifier:
    def __init__(self, *, valid: bool = True, roles: list[str] | None = None) -> None:
        self.valid = valid
        self.roles = roles or []

    async def verify(self, token: str) -> dict | None:
        if not self.valid:
            return None
        claims = {
            "sub": "user-42",
            "realm_access": {"roles": self.roles},
            "resource_access": {"ehos-web": {"roles": ["reader"]}},
        }
        if token == "invalid":  # noqa: S105
            return None
        if token == "expired":  # noqa: S105
            return None
        return claims

    def has_role(self, claims: dict | None, role: str) -> bool:
        if not claims:
            return False
        realm = claims.get("realm_access", {}) or {}
        roles = set(realm.get("roles", []))
        for client in (claims.get("resource_access", {}) or {}).values():
            roles.update(client.get("roles", []))
        return role in roles


def _make_deps(*, valid: bool = True, roles: list[str] | None = None) -> AuthDeps:
    settings = ServiceSettings()
    deps = build_auth_deps(settings)
    deps._verifier = _FakeVerifier(valid=valid, roles=roles)  # noqa: SLF001
    return deps


def _make_app(deps: AuthDeps) -> TestClient:
    app = FastAPI()

    @app.get("/me")
    def me(user: dict = Depends(deps.require())):
        return {"sub": user.get("sub")}

    @app.get("/doctor-only")
    def doctor(user: dict = Depends(deps.require("doctor"))):
        return {"sub": user.get("sub"), "roleCheck": True}

    return TestClient(app)


AUTH = {"Authorization": "Bearer token-a"}


class TestAuthDeps:
    def test_missing_header_rejected(self) -> None:
        client = _make_app(_make_deps())
        assert client.get("/me").status_code == 401

    def test_invalid_token_rejected(self) -> None:
        client = _make_app(_make_deps())
        assert client.get("/me", headers={"Authorization": "Bearer invalid"}).status_code == 401

    def test_valid_token_passes(self) -> None:
        client = _make_app(_make_deps(roles=["patient"]))
        response = client.get("/me", headers=AUTH)
        assert response.status_code == 200
        assert response.json() == {"sub": "user-42"}

    def test_role_required_forbidden_when_missing(self) -> None:
        client = _make_app(_make_deps(roles=["patient"]))
        assert client.get("/doctor-only", headers=AUTH).status_code == 403

    def test_role_required_allowed_when_present(self) -> None:
        client = _make_app(_make_deps(roles=["doctor"]))
        response = client.get("/doctor-only", headers=AUTH)
        assert response.status_code == 200

    def test_resource_role_satisfies_requirement(self) -> None:
        deps = _make_deps(roles=["reader"])
        client = _make_app(deps)
        assert client.get("/doctor-only", headers=AUTH).status_code == 403

    def test_any_role_matches(self) -> None:
        client = _make_app(_make_deps(roles=["writer"]))
        assert client.get("/doctor-only", headers=AUTH).status_code == 403