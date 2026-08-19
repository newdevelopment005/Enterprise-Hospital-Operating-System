"""Tests for idempotency middleware and stores."""

from __future__ import annotations

import pytest

from ehos_common.idempotency import (
    IdempotencyMiddleware,
    MemoryIdempotencyStore,
    RedisIdempotencyStore,
    fingerprint,
)

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _make_app(store):
    app = FastAPI()
    app.add_middleware(IdempotencyMiddleware, store=store)

    @app.post("/orders")
    def create_order(body: dict):
        return {"created": body.get("ref", "unknown")}

    @app.post("/missing")
    def missing(body: dict):
        raise HTTPException(404, "not found")

    return TestClient(app)


class TestFingerprint:
    def test_includes_method_path_body_and_key(self) -> None:
        body_a = b'body-a'
        body_b = b'body-b'
        assert fingerprint("POST", "/orders", body_a, "k1") != fingerprint("POST", "/orders", body_a, "k2")
        assert fingerprint("POST", "/orders", body_a, "k1") != fingerprint("POST", "/orders", body_b, "k1")
        assert fingerprint("POST", "/orders", body_a, "k1") != fingerprint("POST", "/orders2", body_a, "k1")
        assert fingerprint("POST", "/orders", body_a, "k1") != fingerprint("PUT", "/orders", body_a, "k1")
        assert fingerprint("POST", "/orders", body_a, "k1") == fingerprint("post", "/orders", body_a, "k1")

    def test_deterministic(self) -> None:
        assert fingerprint("POST", "/x", b"body", "key") == fingerprint("POST", "/x", b"body", "key")


class TestMemoryIdempotencyStore:
    def test_roundtrip(self) -> None:
        store = MemoryIdempotencyStore()
        assert store.get("fp") is None
        store.set("fp", 201, {"x": "y"}, b"{}", ttl_seconds=60)
        assert store.get("fp") == (201, {"x": "y"}, b"{}")

    def test_ttl_expiry(self) -> None:
        store = MemoryIdempotencyStore()
        store.set("fp", 200, {}, b"{}", ttl_seconds=-1)
        assert store.get("fp") is None


class TestRedisIdempotencyStore:
    def test_missing_returns_none(self) -> None:
        assert RedisIdempotencyStore(_FakeRedis()).get("fp") is None

    def test_roundtrip(self) -> None:
        client = _FakeRedis()
        store = RedisIdempotencyStore(client)
        store.set("fp", 201, {"x-echo": "a"}, b'{"ok":true}', ttl_seconds=60)
        assert store.get("fp") == (201, {"x-echo": "a"}, b'{"ok":true}')

    def test_corrupt_payload_returns_none(self) -> None:
        client = _FakeRedis()
        client.values["ehos:idempotency:fp"] = b"not json"
        assert RedisIdempotencyStore(client).get("fp") is None


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str | bytes] = {}

    def get(self, key: str) -> bytes | None:
        val = self.values.get(key)
        return val.encode("utf-8") if isinstance(val, str) else val

    def set(self, key: str, value: str, *, ex: int | None = None) -> None:  # noqa: ARG002
        self.values[key] = value


class TestIdempotencyMiddleware:
    def test_first_execution_then_replay(self) -> None:
        store = MemoryIdempotencyStore()
        client = _make_app(store)
        r1 = client.post("/orders", json={"ref": "A1"}, headers={"Idempotency-Key": "k1"})
        assert r1.status_code == 200
        assert r1.headers.get("x-ehos-idempotency-replay") is None
        r2 = client.post("/orders", json={"ref": "A1"}, headers={"Idempotency-Key": "k1"})
        assert r2.status_code == 200
        assert r2.json() == r1.json()
        assert r2.headers.get("x-ehos-idempotency-replay") == "true"

    def test_different_key_is_not_a_replay(self) -> None:
        store = MemoryIdempotencyStore()
        client = _make_app(store)
        client.post("/orders", json={"ref": "A1"}, headers={"Idempotency-Key": "k1"})
        r2 = client.post("/orders", json={"ref": "A1"}, headers={"Idempotency-Key": "k2"})
        assert r2.headers.get("x-ehos-idempotency-replay") is None

    def test_same_key_different_body_is_not_a_replay(self) -> None:
        store = MemoryIdempotencyStore()
        client = _make_app(store)
        client.post("/orders", json={"ref": "A1"}, headers={"Idempotency-Key": "k1"})
        r2 = client.post("/orders", json={"ref": "B9"}, headers={"Idempotency-Key": "k1"})
        assert r2.json() == {"created": "B9"}
        assert r2.headers.get("x-ehos-idempotency-replay") is None

    def test_without_key_is_transparent(self) -> None:
        store = MemoryIdempotencyStore()
        client = _make_app(store)
        r1 = client.post("/orders", json={"ref": "A1"})
        r2 = client.post("/orders", json={"ref": "A1"})
        assert r1.headers.get("x-ehos-idempotency-replay") is None
        assert r2.headers.get("x-ehos-idempotency-replay") is None

    def test_errors_are_also_idempotent(self) -> None:
        store = MemoryIdempotencyStore()
        client = _make_app(store)
        r1 = client.post("/missing", json={}, headers={"Idempotency-Key": "k404"})
        assert r1.status_code == 404
        r2 = client.post("/missing", json={}, headers={"Idempotency-Key": "k404"})
        assert r2.status_code == 404
        assert r2.headers.get("x-ehos-idempotency-replay") == "true"

    def test_get_is_not_idempotent_keyed(self) -> None:
        store = MemoryIdempotencyStore()
        client = _make_app(store)
        client.get("/orders")
        client.get("/orders")
        assert store.get(fingerprint("GET", "/orders", b"", "whatever")) is None