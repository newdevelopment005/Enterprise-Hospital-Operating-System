"""Shared liveness/readiness endpoints.

Every EHOS service must expose a GET /health so that Kubernetes readiness and
liveness probes (``infrastructure/kubernetes/09-app-services.yaml`` and the Helm
``templates/deployment.yaml``) can mark the pod Ready. Including this router
gives each service a consistent, dependency-free endpoint.

The ``/metrics`` route is exported here too so Prometheus can scrape every
service through the same router; the MetricsMiddleware populates it when wired
in (see :mod:`ehos_common.metrics`).
"""

from fastapi import APIRouter

from ehos_common.metrics import metrics_router

health_router = APIRouter(tags=["health"])
health_router.include_router(metrics_router)


@health_router.get("/health", operation_id="healthz")
async def health() -> dict:
    """Simple liveness/readiness probe used by Kubernetes and compose healthchecks."""
    return {"status": "ok", "service": "ehos"}


@health_router.get("/healthz", operation_id="healthz_live")
async def healthz() -> dict:
    """Alias used by some ingress healthchecks."""
    return {"status": "ok"}