"""Idempotency keys for at-least-once API semantics.

Provides a Starlette middleware (the AWS/POSTMAN idempotency-proxy pattern):

- requests carrying an ``Idempotency-Key`` header on ``POST``/``PUT``/``PATCH``
  are fingerprinted from method + path + body;
- a repeated request with the same key returns the **original stored response**
  (status, body, headers) instead of re-executing the handler;
- on the first execution the response is stored for ``ttl_seconds``.

This makes client retries safe: re-sending a request after a timeout or network
failure cannot create duplicate patients/notes/orders.

Storage is abstracted so tests use the in-memory store and production uses
Redis. With no store configured the middleware is transparent.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import time

_IDEMPOTENCY_METHODS = {"POST", "PUT", "PATCH"}
_IDEMPOTENCY_HEADER = "idempotency-key"

_EXCLUDED_PREFIXES = ("/health", "/healthz", "/metrics", "/docs", "/api/v1/openapi.json")


class IdempotencyStore:
    """Store/load committed idempotency responses keyed by fingerprint."""

    def get(self, fingerprint: str) -> tuple[int, dict, bytes] | None:
        """Return (status_code, headers, body) for a stored response, else None."""
        raise NotImplementedError

    def set(self, fingerprint: str, status: int, headers: dict, body: bytes, ttl_seconds: int) -> None:
        raise NotImplementedError


class MemoryIdempotencyStore(IdempotencyStore):
    """Process-local store with TTL. Suited to tests and single-replica dev."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, tuple[int, dict, bytes]]] = {}

    def get(self, fingerprint: str) -> tuple[int, dict, bytes] | None:
        entry = self._data.get(fingerprint)
        if entry is None:
            return None
        until, payload = entry
        if until < time.monotonic():
            self._data.pop(fingerprint, None)
            return None
        return payload

    def set(self, fingerprint: str, status: int, headers: dict, body: bytes, ttl_seconds: int) -> None:
        self._data[fingerprint] = (time.monotonic() + ttl_seconds, (status, headers, body))

    def clear(self) -> None:
        self._data.clear()


class RedisIdempotencyStore(IdempotencyStore):
    """Redis-backed store using the shared synchronous client family."""

    NAMESPACE = "ehos:idempotency"

    def __init__(self, client):
        self._client = client

    def _key(self, fingerprint: str) -> str:
        return f"{self.NAMESPACE}:{fingerprint}"

    def get(self, fingerprint: str) -> tuple[int, dict, bytes] | None:
        try:
            raw = self._client.get(self._key(fingerprint))
        except Exception:  # noqa: BLE001 - idempotency must never crash the app
            return None
        if not raw:
            return None
        try:
            payload = json.loads(raw.decode("utf-8"))
            return int(payload["status"]), payload.get("headers", {}), payload["body"].encode("utf-8")
        except (ValueError, KeyError, TypeError, AttributeError):
            return None

    def set(self, fingerprint: str, status: int, headers: dict, body: bytes, ttl_seconds: int) -> None:
        payload = json.dumps({"status": status, "headers": headers, "body": body.decode("utf-8", "replace")})
        with contextlib.suppress(Exception):  # noqa: S110 - degrade gracefully
            self._client.set(self._key(fingerprint), payload, ex=ttl_seconds)


def fingerprint(method: str, path: str, body: bytes, key: str) -> str:
    """Deterministic digest of the request; safe to index in Redis.

    The idempotency key is part of the identity: a *different* key always means a
    *different* logical operation, even when method/path/body match, so each key
    gets its own stored result.
    """
    material = hashlib.sha256()
    material.update(method.upper().encode("utf-8"))
    material.update(b"|")
    material.update(path.encode("utf-8"))
    material.update(b"|")
    material.update(key.encode("utf-8"))
    material.update(b"|")
    material.update(body)
    return material.hexdigest()


def default_store(redis_client=None) -> IdempotencyStore:
    """Pick a store: Redis when a client is available, else the process-local one.

    ``redis_client`` is the shared ehos-common synchronous client; if None (local
    dev, no Redis) the middleware still works but only within a single process.
    """
    if redis_client is not None:
        return RedisIdempotencyStore(redis_client)
    return MemoryIdempotencyStore()


class IdempotencyMiddleware:
    """Keyed idempotent requests for POST/PUT/PATCH with an ``Idempotency-Key``.

    Buffers the request body, looks up the fingerprint in the store, and either
    short-circuits with the stored response or runs the app and stores the result.
    """

    def __init__(self, app, store: IdempotencyStore | None = None, ttl_seconds: int = 86400):
        self.app = app
        self.store = store
        self.ttl_seconds = ttl_seconds

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or self.store is None:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        path = scope.get("path", "")
        if method not in _IDEMPOTENCY_METHODS or path.startswith(_EXCLUDED_PREFIXES):
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        key = headers.get(_IDEMPOTENCY_HEADER)
        if not key:
            await self.app(scope, receive, send)
            return

        body, replay_receive = await self._buffer_body(receive)
        fingerprint_key = fingerprint(method, path, body, key)

        stored = self.store.get(fingerprint_key)
        if stored is not None:
            status, header_map, stored_body = stored
            response_headers = [
                (k.encode("latin-1"), v.encode("latin-1")) for k, v in header_map.items()
            ]
            response_headers.append((b"x-ehos-idempotency-replay", b"true"))
            await send({"type": "http.response.start", "status": status, "headers": response_headers})
            await send({"type": "http.response.body", "body": stored_body})
            return

        status, header_map, response_body = await self._run_and_capture(scope, replay_receive)
        self.store.set(fingerprint_key, status, header_map, response_body, self.ttl_seconds)

        response_headers = [
            (k.encode("latin-1"), v.encode("latin-1")) for k, v in header_map.items()
        ]
        await send({"type": "http.response.start", "status": status, "headers": response_headers})
        if response_body:
            await send({"type": "http.response.body", "body": response_body})

    @staticmethod
    async def _buffer_body(receive):
        """Buffer the incoming body, returning (bytes, a receive() that replays it).

        The app runs exactly once; ``replay_receive`` serves the buffered body in
        a single ``http.request`` message, followed by an empty tail message.
        """
        chunks: list[bytes] = []
        while True:
            message = await receive()
            if message["type"] != "http.request":
                continue
            chunks.append(message.get("body", b""))
            if not message.get("more_body"):
                break
        body = b"".join(chunks)
        replayed = False

        async def replay_receive():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        return body, replay_receive

    async def _run_and_capture(self, scope, receive):
        """Run the app once, capturing status, headers and body without touching the client socket."""
        captured: dict = {"status": 200, "headers": {}, "body": b""}
        body_parts: list[bytes] = []

        async def send_capture(message):
            if message["type"] == "http.response.start":
                captured["status"] = message["status"]
                captured["headers"] = {
                    k.decode("latin-1"): v.decode("latin-1")
                    for k, v in message.get("headers", [])
                    if k.decode("latin-1").lower() not in {"content-length", "content-type", "date", "server"}
                }
            elif message["type"] == "http.response.body" and message.get("body"):
                body_parts.append(message["body"])

        await self.app(scope, receive, send_capture)
        captured["body"] = b"".join(body_parts)
        return captured["status"], captured["headers"], captured["body"]