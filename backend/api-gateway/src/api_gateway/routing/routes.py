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
- appointment-service:    ``/api/v1/appointments`` (booking, reschedule, cancel)
- queue-service:          ``/api/v1/queues`` (digital queues, tickets)
- billing-service:        ``/api/v1/billing`` (charges, invoices, payments)
- prescription-service:   ``/api/v1/prescriptions`` (prescribing, MAR, allergies)
- pharmacy-service:       ``/api/v1/pharmacy`` (catalog, stock, dispensing)
- laboratory-service:     ``/api/v1/laboratory`` (test catalog, orders, samples, results)
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

from typing import NotRequired, TypedDict


class RouteConfig(TypedDict):
    upstream: str
    requires_auth: bool
    required_role: str | None
    rewrite_prefix: NotRequired[str]


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
    "/api/v1/appointments": {
        "upstream": "http://appointment-service:8503",
        "requires_auth": True,
        "required_role": None,
    },
    "/api/v1/queues": {
        "upstream": "http://queue-service:8504",
        "requires_auth": True,
        "required_role": None,
    },
    "/api/v1/billing": {
        "upstream": "http://billing-service:8509",
        "requires_auth": True,
        "required_role": None,
    },
    "/api/v1/prescriptions": {
        "upstream": "http://prescription-service:8510",
        "requires_auth": True,
        "required_role": None,
    },
    "/api/v1/pharmacy": {
        "upstream": "http://pharmacy-service:8511",
        "requires_auth": True,
        "required_role": None,
    },
    "/api/v1/laboratory": {
        "upstream": "http://laboratory-service:8512",
        "requires_auth": True,
        "required_role": None,
    },
    "/api/v1/radiology": {
        "upstream": "http://radiology-service:8513",
        "requires_auth": True,
        "required_role": None,
    },
    "/api/v1/inventory": {
        "upstream": "http://inventory-service:8514",
        "requires_auth": True,
        "required_role": None,
    },
    "/api/v1/workflows": {
        "upstream": "http://workflow-service:8515",
        "requires_auth": True,
        "required_role": None,
    },
    "/api/v1/documentation": {
        "upstream": "http://clinical-documentation-service:8516",
        "requires_auth": True,
        "required_role": None,
    },
    "/api/v1/insurance": {
        "upstream": "http://insurance-service:8517",
        "requires_auth": True,
        "required_role": None,
    },
    "/api/v1/reporting": {
        "upstream": "http://reporting-service:8518",
        "requires_auth": True,
        "required_role": None,
    },
    "/api/v1/analytics": {
        "upstream": "http://analytics-service:8508",
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
    "/api/v1/all": {
        "upstream": "http://configuration-service:8100",
        "requires_auth": True,
        "required_role": None,
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
    # Frontend short prefixes (used by the ehr-portal Vite proxy and NGINX
    # rewrites). Held in the gateway so every client reaches services through a
    # single entry point; each forwards to the canonical /api/v1 path by
    # stripping the wire prefix (see apply_rewrite).
    "/mpi": {"upstream": "http://patient-service:8501", "requires_auth": True, "required_role": None, "rewrite_prefix": "/mpi"},
    "/sched": {"upstream": "http://appointment-service:8503", "requires_auth": True, "required_role": None, "rewrite_prefix": "/sched"},
    "/q": {"upstream": "http://queue-service:8504", "requires_auth": True, "required_role": None, "rewrite_prefix": "/q"},
    "/bill": {"upstream": "http://billing-service:8509", "requires_auth": True, "required_role": None, "rewrite_prefix": "/bill"},
    "/rx": {"upstream": "http://prescription-service:8510", "requires_auth": True, "required_role": None, "rewrite_prefix": "/rx"},
    "/pharm": {"upstream": "http://pharmacy-service:8511", "requires_auth": True, "required_role": None, "rewrite_prefix": "/pharm"},
    "/lab": {"upstream": "http://laboratory-service:8512", "requires_auth": True, "required_role": None, "rewrite_prefix": "/lab"},
    "/rad": {"upstream": "http://radiology-service:8513", "requires_auth": True, "required_role": None, "rewrite_prefix": "/rad"},
    "/inv": {"upstream": "http://inventory-service:8514", "requires_auth": True, "required_role": None, "rewrite_prefix": "/inv"},
    "/wf": {"upstream": "http://workflow-service:8515", "requires_auth": True, "required_role": None, "rewrite_prefix": "/wf"},
    "/doc": {"upstream": "http://clinical-documentation-service:8516", "requires_auth": True, "required_role": None, "rewrite_prefix": "/doc"},
    "/ins": {"upstream": "http://insurance-service:8517", "requires_auth": True, "required_role": None, "rewrite_prefix": "/ins"},
    "/rpt": {"upstream": "http://reporting-service:8518", "requires_auth": True, "required_role": None, "rewrite_prefix": "/rpt"},
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


def apply_rewrite(path: str, route: RouteConfig) -> str:
    """Strip a frontend wire prefix so the upstream sees its canonical path."""
    rewrite_prefix = route.get("rewrite_prefix")
    if rewrite_prefix and path.startswith(rewrite_prefix):
        stripped = path[len(rewrite_prefix):]
        return stripped or "/"
    return path