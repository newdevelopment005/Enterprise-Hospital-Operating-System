"""Redis client wrapper used for caching, rate limiting, and sessions."""

from __future__ import annotations

import json

import redis
import redis.asyncio as aioredis


class RedisClient:
    def __init__(self, host: str, port: int, password: str | None = None):
        self.host = host
        self.port = port
        self.password = password
        self._client: aioredis.Redis | None = None

    async def start(self) -> None:
        self._client = aioredis.Redis(host=self.host, port=self.port, password=self.password, decode_responses=True)
        await self._client.ping()

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> aioredis.Redis:
        if self._client is None:
            raise RuntimeError("Redis client not started")
        return self._client

    async def set_json(self, key: str, value: object, ttl_seconds: int | None = None) -> None:
        await self.client.set(key, json.dumps(value), ex=ttl_seconds)

    async def get_json(self, key: str) -> object | None:
        raw = await self.client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def delete(self, key: str) -> None:
        await self.client.delete(key)


class RateLimiterRedis(redis.Redis):
    """Sliding-window rate limiter backed by Redis (used by the api-gateway)."""

    def sliding_window_check(self, key: str, limit: int, window_seconds: int) -> bool:
        score = float(self.get(key) or 0)
        if score >= limit:
            return False
        pipeline = self.pipeline()
        pipeline.incr(key)
        pipeline.expire(key, window_seconds)
        pipeline.execute()
        return True