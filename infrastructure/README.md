# Infrastructure (Phase 0)

Local development stack for the EHOS Foundation Platform.

## What runs

| Service | Port | Notes |
|---|---|---|
| Postgres 16 | 5432 | One database per service (init script creates them) |
| Redis 7 | 6379 | Cache, rate limiting |
| Kafka (KRaft) | 9092 | Event bus |
| MinIO | 9000/9001 | Object storage |
| Keycloak 25 | 8400 | Identity (realm auto-imported) |
| API Gateway | 8000 | FastAPI gateway |
| Configuration | 8100 | |
| Audit | 8200 | |
| Notification | 8300 | |

Monitoring (optional profile) adds Prometheus (9090), Grafana (3000), Loki (3100), Tempo (3200).

## Start

```bash
# from repository root
cp .env.example .env          # then edit secrets
make init
make build                    # build the Python service images
make up                       # infrastructure + services
docker compose -f infrastructure/docker-compose.yml --profile monitoring up -d   # monitoring
```

## Verification

```bash
make ps
curl http://localhost:8100/docs
curl http://localhost:8200/docs
curl http://localhost:8300/docs
```

Keycloak admin console: http://localhost:8400/admin

## Notes

- The Phase 0 Python services are FastAPI; the docs (`AUTHENTICATION.md`) mandate
  Keycloak for identity rather than a bespoke auth service.
- In production, container orchestration moves to Kubernetes/Helm
  (see `EHOS_ARCHITECTURE_DESIGN.md` deployment section).