"""Reverse-proxy forwarding: streams requests to upstream services.

A catch-all route inspects the path and dispatches to the configured upstream,
correlating with ``X-Request-Id``. Access is logged per CODING_STANDARDS.md.
"""

import time

import httpx
import structlog
from ehos_common.logging import bind_request, elapsed
from fastapi import APIRouter, Request
from starlette.responses import Response

log = structlog.get_logger("api-gateway")

proxy_router = APIRouter()


@proxy_router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(request: Request, path: str) -> Response:
    from api_gateway.routing.routes import match_route

    start = time.perf_counter()
    route = match_route(request.url.path)
    if route is None:
        _access_log(request, 404, start)
        return Response(status_code=404)

    upstream_base = route["upstream"]
    raw_path = request.url.path
    query = request.url.query
    target_url = f"{upstream_base}{raw_path}" + (f"?{query}" if query else "")
    headers = {key: value for key, value in request.headers.items() if key.lower() not in {"host"}}
    headers["X-Request-Id"] = request.state.request_id

    body = await request.body()
    timeout = httpx.Timeout(30)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            upstream_response = await client.request(request.method, target_url, headers=headers, content=body)
        except httpx.HTTPError:
            _access_log(request, 502, start)
            return Response(
                status_code=502,
                content=b'{"success": false, "errorCode": "BAD_GATEWAY", "message": "Upstream unavailable"}',
            )

    _access_log(request, upstream_response.status_code, start)
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=_forward_headers(upstream_response.headers, request.state.request_id),
    )


def _forward_headers(upstream: httpx.Headers, request_id: str) -> dict[str, str]:
    """Forward the upstream media type and the headers clients rely on.

    Hop-by-hop headers (transfer-encoding, content-length, connection, ...) are
    rebuilt by the ASGI server and must not be copied; a curated whitelist keeps
    JSON/other media types, auth challenge, cookies and redirects intact.
    """
    keep = {
        "content-type",
        "content-disposition",
        "set-cookie",
        "www-authenticate",
        "location",
        "cache-control",
        "etag",
        "retry-after",
    }
    out = {key: value for key, value in upstream.items() if key.lower() in keep}
    out["X-Request-Id"] = request_id
    return out


def _access_log(request: Request, status_code: int, start: float) -> None:
    request_id = request.state.request_id
    user_id = request.state.user_id
    op = f"{request.method} {request.url.path}"
    bound = bind_request(log, request_id=request_id, user_id=user_id, operation=op)
    bound.info(
        "gateway_access",
        status=status_code,
        clientIp=request.client.host if request.client else None,
        duration=elapsed(start),
        result="ok" if status_code < 400 else "error",
    )