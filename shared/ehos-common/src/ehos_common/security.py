"""Security helpers: JWT validation against Keycloak JWKS and Role-Based Access Control.

Zero-trust: every request is authenticated at the API gateway via Keycloak OIDC.
This module provides a cached JWKS client and claim-based authorization helpers
used by service middlewares.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from jose import jwk, jwt


class JWTVerifier:
    """Validates RS256 JWTs issued by Keycloak using cached JWKS keys."""

    def __init__(self, jwks_url: str, issuer: str, audience: str):
        self.jwks_url = jwks_url
        self.issuer = issuer
        self.audience = audience
        self._keys: dict[str, RSAPublicKey] | None = None
        self._fetched_at: float = 0.0
        self.cache_ttl = 300

    async def _load_keys(self) -> dict[str, RSAPublicKey] | None:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(self.jwks_url)
            response.raise_for_status()
        jwks: dict[str, Any] = response.json()
        keys: dict[str, RSAPublicKey] = {}
        for entry in jwks.get("keys", []):
            key_id = entry.get("kid")
            if key_id:
                rsa_key = jwk.RSAKey(entry, algorithm="RS256")
                keys[key_id] = rsa_key.public_key().to_pem()
        return keys

    async def _get_keys(self) -> dict[str, RSAPublicKey] | None:
        if self._keys is None or (time.time() - self._fetched_at) > self.cache_ttl:
            self._keys = await self._load_keys()
            self._fetched_at = time.time()
        return self._keys

    async def verify(self, token: str) -> dict[str, Any] | None:
        """Return validated claims, or None if the token is invalid/expired."""
        try:
            keys = await self._get_keys()
            if not keys:
                return None
            header = jwt.get_unverified_header(token)
            public_key = keys.get(header.get("kid", ""))
            if public_key is None:
                return None
            claims = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
                options={"verify_aud": True},
            )
            return claims
        except (jwt.JWTError, KeyError, httpx.HTTPError):
            return None

    def has_role(self, claims: dict[str, Any] | None, role: str) -> bool:
        if not claims:
            return False
        realm_access = claims.get("realm_access", {}) or {}
        roles = set(realm_access.get("roles", []))
        resource_access = claims.get("resource_access", {}) or {}
        for client in resource_access.values():
            roles.update(client.get("roles", []))
        return role in roles


_client_verifiers: dict[str, JWTVerifier] = {}


def get_verifier(jwks_url: str, issuer: str, audience: str) -> JWTVerifier:
    cache_key = f"{jwks_url}|{issuer}|{audience}"
    if cache_key not in _client_verifiers:
        _client_verifiers[cache_key] = JWTVerifier(jwks_url, issuer, audience)
    return _client_verifiers[cache_key]