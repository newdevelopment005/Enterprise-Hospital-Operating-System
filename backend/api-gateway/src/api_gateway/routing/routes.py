"""Route table for the API gateway.

Defines which upstream service handles each path prefix, whether the route
requires authentication, and any minimum role required.

The prefixes and upstreams below match the *actual* FastAPI route prefixes each
service exposes (see ``backend/<service>/src/<svc>/api/routes.py``):

- configuration-service:  ``/api/v1/flags``, ``/api/v1/entries``, ``/api/v1/all``
- audit-service:          ``/api/v1/records``, ``/api/v1/integrity``
- notification-service:   ``/api/v1/templates``, ``/api/v1/send``
- authentication-service: ``/api/v1/auth`` (public + self-protected endpoints)
- patient-service:        ``/api/v1/patients`` (demographics, merge)
- ehr-service:            ``/api/v1/ehr`` (clinical record sub-resources)
- ai-service:             ``/api/v1/ai``
- knowledge-service:      ``/api/v1/knowledge``
- prediction-service:     ``/api/v1/predictions``

``/api/v1/ehr`` is used (rather than ``/api/v1/patients/...``) to disambiguate
the clinical record from patient demographics; both services previously claimed
the overlapping ``/api/v1/patients/{id}/...`` namespace.

Production deployments may use Kong/Envoy/NGINX as the gateway; this FastAPI
gateway mirrors the same routing contract for development.
"""

from typing import TypedDict


class RouteConfig(TypedDict):
    upstream: str
    requires_auth: bool
    required_role: str | None


ROUTES: dict[str, RouteConfig] = {
    "/api/v1/auth": {
        "upstream": "http://authentication-service:8500",
        "requires_auth": False,  # public flows; service self-protects its admin endpoints
        "required_role": None,
    },
    "/api/v1/ehr": {
        "upstream": "http://ehr-service:8502",
        "requires_auth": True,
        "required_role": None,
    },
    "/api/v1/patients": {
        "upstream": "http://patient-service:8501",
        "requires_auth": True,
        "required_role": None,
    },
    "/api/v1/ai": {
        "upstream": "http://ai-service:8506",
        "requires_auth": True,
        "required_role": None,
    },
    "/api/v1/knowledge": {
        "upstream": "http://knowledge-service:8505",
        "requires_auth": True,
        "required_role": None,
    },
    "/api/v1/predictions": {
        "upstream": "http://prediction-service:8507",
        "requires_auth": True,
        "required_role": None,
    },
    "/api/v1/records": {
        "upstream": "http://audit-service:8200",
        "requires_auth": True,
        "required_role": None,
    },
    "/api/v1/integrity": {
        "upstream": "http://audit-service:8200",
        "requires_auth": True,
        "required_role": None,
    },
    "/api/v1/flags": {
        "upstream": "http://configuration-service:8100",
        "requires_auth": True,
        "required_role": "administrator",
    },
    "/api/v1/entries": {
        "upstream": "http://configuration-service:8100",
        "requires_auth": True,
        "required_role": "administrator",
    },
    "/api/v1/templates": {
        "upstream": "http://notification-service:8300",
        "requires_auth": True,
        "required_role": None,
    },
    "/api/v1/send": {
        "upstream": "http://notification-service:8300",
        "requires_auth": True,
        "required_role": None,
    },
}


def match_route(path: str) -> RouteConfig | None:
    """Return the most specific route config for a request path."""
    best: tuple[int, RouteConfig] | None = None
    for prefix, config in ROUTES.items():
        if not path.startswith(prefix):
            continue
        if best is None or len(prefix) > best[0]:
            best = (len(prefix), config)
    return best[1] if best else None