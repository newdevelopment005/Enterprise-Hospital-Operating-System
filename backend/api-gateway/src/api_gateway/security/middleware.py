"""Gateway middlewares: JWT validation, rate limiting, request correlation.

Order of operations per request:
1. Assign/capture a request-id (correlation id).
2. Enforce rate limits.
3. Validate the JWT (when the route requires auth) and check roles.
4. Forward to the upstream service.

Middleware dependencies (verifier, redis) are resolved from ``request.app.state``
at dispatch time because the application lifespan populates them after
middleware construction.
"""

import asyncio
import logging
import time
import uuid

from ehos_common.api import _error_payload
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# Operational endpoints that must stay reachable even if upstream routing or
# Redis is unavailable; they are exempt from rate limiting and auth.
_EXCLUDED_PATHS = {"/health", "/healthz", "/metrics", "/docs", "/openapi.json", "/api/v1/openapi.json"}


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.user_id = None
        request.state.start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limit keyed by client IP."""

    def __init__(self, app, limit: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.limit = limit
        self.window_seconds = window_seconds

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _EXCLUDED_PATHS:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        key = f"ehos:ratelimit:{client_ip}:{request.url.path}"
        redis_client = request.app.state.redis
        if redis_client is None:
            logger.warning("rate_limit_redis_unavailable", extra={"path": request.url.path})
            return await call_next(request)
        # Run the blocking Redis call off the event loop.
        try:
            allowed = await asyncio.to_thread(
                redis_client.sliding_window_check, key, self.limit, self.window_seconds
            )
        except Exception:
            logger.exception("rate_limit_check_failed", extra={"path": request.url.path})
            return await call_next(request)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content=_error_payload("RATE_LIMITED", "Too many requests. Please try again later."),
                headers={"Retry-After": str(self.window_seconds)},
            )
        return await call_next(request)


class AuthMiddleware(BaseHTTPMiddleware):
    """Validates the Bearer JWT and enforces route-level roles."""

    async def dispatch(self, request: Request, call_next) -> Response:
        from api_gateway.routing.routes import match_route

        if request.url.path in _EXCLUDED_PATHS:
            return await call_next(request)

        route = match_route(request.url.path)
        if route is None:
            return JSONResponse(
                status_code=404,
                content=_error_payload("NOT_FOUND", "No route configured for this path"),
            )

        if route["requires_auth"]:
            verifier = request.app.state.verifier
            authorization = request.headers.get("Authorization", "")
            if not authorization.startswith("Bearer "):
                return JSONResponse(
                    status_code=401,
                    content=_error_payload("UNAUTHORIZED", "Authentication required"),
                )
            token = authorization.removeprefix("Bearer ")
            claims = await verifier.verify(token)
            if claims is None:
                return JSONResponse(
                    status_code=401,
                    content=_error_payload("UNAUTHORIZED", "Token is invalid or expired"),
                )
            request.state.user_id = claims.get("sub")
            required_role = route["required_role"]
            if required_role and not verifier.has_role(claims, required_role):
                return JSONResponse(
                    status_code=403,
                    content=_error_payload("FORBIDDEN", f"Role '{required_role}' is required"),
                )

        return await call_next(request)