# API Gateway

EHOS single entry point (Phase 0).

## Responsibilities

- Route to upstream services (`routing/routes.py`).
- JWT validation against Keycloak JWKS (zero-trust, never trusts internal callers by default).
- Route-level role enforcement.
- Sliding-window rate limiting by client IP via Redis.
- `X-Request-Id` correlation and structured access logging.

## Routing contract

| Prefix | Upstream | Auth | Required role |
|---|---|---|---|
| `/api/v1/configuration` | configuration-service:8100 | Yes | `administrator` |
| `/api/v1/audit` | audit-service:8200 | Yes | — |
| `/api/v1/notifications` | notification-service:8300 | Yes | — |

Production deployments may replace this FastAPI gateway with Kong/Envoy/NGINX
using the same routing contract (TECH_STACK.md section 7).

## Local development

```bash
pip install -e ../../shared/ehos-common -e .
uvicorn api_gateway.main:app --host 0.0.0.0 --port 8000
```

## Security notes

- Tokens validated against Keycloak JWKS (cached 5 minutes).
- Rate limiter keyed by client IP; tune `limit`/`window_seconds` as needed.
- Secrets are handled by Vault, never committed.