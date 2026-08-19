# EHOS - Enterprise Hospital Operating System

An AI-native, event-driven, offline-first hospital operating system built for
enterprise-scale care delivery. See the [architecture baseline](EHOS_ARCHITECTURE_DESIGN.md)
and the supporting documents in this repository for the full design.

> The current build state is **Phase 0: Foundation Platform** with the frontend
> apps (`frontend/apps/`) in place; see `CHANGELOG.md`.

## Repository layout

```text
├── docs (architecture documents)     # *.md at repository root
├── backend/
│   ├── api-gateway/                  # FastAPI gateway (routing, auth, rate limiting)
│   ├── identity-service/             # Keycloak realm & configuration
│   ├── configuration-service/        # Feature flags, reference configuration
│   ├── audit-service/                # Immutable audit records
│   └── notification-service/         # SMS / Email / Push / In-app notifications
├── frontend/
│   └── apps/
│       ├── executive-dashboard/      # Executive Command Center (KPIs, forecasts, AI insights)
│       ├── ehr-portal/               # Clinical EHR portal
│       ├── ai-assistant/             # HospitalGPT chat UI
│       └── patient-registration/     # Patient intake/registration
├── shared/
│   └── ehos-common/                  # Cross-cutting Python library
├── infrastructure/                   # Docker Compose (dev + prod), Kubernetes YAML, Helm, backup
├── monitoring/                       # Prometheus, Grafana, Loki, Tempo
├── security/                         # Policies, certificates
├── scripts/                          # Development & operational scripts
└── .github/workflows/                # CI/CD
```

## Phase 0: Foundation Platform

Phase 0 establishes the technical foundation:

| Service | Responsibility |
|---|---|
| `api-gateway` | Single entry point, routing, JWT validation, rate limiting |
| `identity-service` | Identity, SSO, OAuth2/OIDC, MFA (Keycloak) |
| `audit-service` | Immutable, tamper-evident audit trail |
| `notification-service` | Outbound notifications across channels |
| `configuration-service` | Feature flags and reference configuration |

## Quick start

Prerequisites: Docker + Docker Compose, Python 3.11+.

```bash
make init          # create .env and data directories
make up            # start the full stack
make ps            # verify health
```

Service endpoints (development):

| Service | URL | Docs |
|---|---|---|
| API Gateway | http://localhost:8000 | `/docs` |
| Configuration | http://localhost:8100 | `/docs` |
| Audit | http://localhost:8200 | `/docs` |
| Notification | http://localhost:8300 | `/docs` |
| Keycloak | http://localhost:8400 | `/admin` |

## Standards compliance

All services follow the repository standards:

- `CODING_STANDARDS.md` - code structure, naming, logging, exceptions, events.
- `EVENT_BUS.md` - event envelope and topic naming.
- `API_DESIGN_STANDARD.md` - versioned APIs, response/error envelopes.
- `DATABASE_STANDARDS.md` - database-per-service, audit fields, retention.
- `SECURITY.md` - zero-trust, secrets management, audit logging.
