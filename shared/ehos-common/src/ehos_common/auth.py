"""Shared FastAPI authentication/authorization dependencies for EHOS services.

Data-plane services sit behind the gateway, which authenticates via Keycloak and
forwards the bearer token. These dependencies re-validate the JWT (never trust
the proxy blindly) and surface the actor's claims plus RBAC checks to endpoints:

.. code-block:: python

    auth = build_auth_deps(settings)

    @app.post("/patients")
    async def register(body: ..., user: dict = Depends(auth.require("doctor"))): ...

``subject`` is the Keycloak user-id / client-id and ``roles`` are the collection
of realm + resource roles. Tokens are verified against the cached JWKS through
:class:`ehos_common.security.JWTVerifier`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ehos_common.config import ServiceSettings
from ehos_common.security import JWTVerifier, get_verifier

_bearer = HTTPBearer(auto_error=False)


class AuthDeps:
    """Ready-to-wire dependencies bound to a service's settings."""

    def __init__(self, settings: ServiceSettings):
        self.settings = settings
        self._verifier: JWTVerifier = get_verifier(
            settings.jwks_url,
            issuer=settings.issuer,
            audience="account",
        )

    @property
    def verifier(self) -> JWTVerifier:
        return self._verifier

    async def current_user(
        self,
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    ) -> dict[str, Any]:
        """Validate the bearer token and return its claims, or raise 401."""
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid Authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = credentials.credentials
        claims = await self._verifier.verify(token)
        if claims is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return claims

    def require(self, *roles: str) -> Callable[..., Any]:
        """Return a dependency requiring the caller to hold at least one of *roles*.

        With no roles passed the dependency only authenticates (any logged-in
        user). Returns the validated claims on success, else 401/403.
        """

        async def dependency(
            claims: dict[str, Any] = Depends(self.current_user),
        ) -> dict[str, Any]:
            if roles and not any(self._verifier.has_role(claims, role) for role in roles):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Requires one of roles: {', '.join(sorted(roles))}",
                )
            return claims

        return dependency

    # Backwards-compatible friendly alias.
    require_any = require


def build_auth_deps(settings: ServiceSettings) -> AuthDeps:
    """Create an :class:`AuthDeps` bound to *settings*."""
    return AuthDeps(settings)