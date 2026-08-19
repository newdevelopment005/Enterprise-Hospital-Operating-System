# DEPLOYMENT_ARCHITECTURE.md

# Enterprise Hospital Operating System (EHOS)

# Production Deployment Architecture

**Version:** 1.0.0
**Document Type:** Operational Deployment Blueprint (concrete artifacts)
**Audience:** DevOps Engineers, Infrastructure Teams, Hospital IT

This document is the concrete, buildable deployment blueprint for EHOS. It
implements the standards in `DEPLOYMENT.md`, `DEVOPS_CICD_PLATFORM_ARCHITECTURE.md`,
`INFRASTRUCTURE_DEPLOYMENT_ARCHITECTURE.md` and `EHOS_ARCHITECTURE_DESIGN.md` and
maps each required technology to a real artifact in this repository.

---

# 1. Deployment Topology

```
                 Clients (Web / Mobile / Kiosk / HL7 Connectors)
                               │  TLS 1.3
                               ▼
        ┌────────────────────────────────────────────┐
        │  Edge: HAProxy (haproxy) L4/L7 load balancer│   port 443/80
        │  redundancy: keepalived VIP, active+standby │
        └────────────────────────────────────────────┘
                               │  443
                               ▼
        ┌────────────────────────────────────────────┐
        │  NGINX Ingress Controller (nginx)          │   ingress cluster
        │  TLS termination via Cert Manager (cert)   │   /api/... routes
        └────────────────────────────────────────────┘
                               │
          ┌────────────────────┼──────────────────────┐
          ▼                    ▼                      ▼
 ┌────────────────┐   ┌──────────────────┐   ┌────────────────────┐
 │ Platform ns    │   │ Clinical services│   │ AI / data plane    │
 │ api-gateway    │   │ ehr-service      │   │ knowledge-service  │
 │ authentication │   │ patient-service  │   │ ai-service         │
 │ configuration  │   │ frontend web apps│   │ prediction-service │
 │ audit/notify   │   │ (ehr-portal,     │   │ inference (GPU)    │
 │                 │   │  patient-reg,   │   │  vllm / ollama     │
 │                 │   │  dashboards,    │   │  qdrant            │
 │                 │   │  ai-assistant)  │   └────────────────────┘
 └────────────────┘   └──────────────────┘
                               │
     ┌──────────────┬──────────┼───────────┬─────────────┬───────────────┐
     ▼              ▼          ▼           ▼             ▼               ▼
 PostgreSQL 16  Redis 7   Kafka KRaft   MinIO (S3)   Qdrant           Keycloak
 (per-svc DBs, (cache /  (event bus,   (objects,     (vector DB,      (OIDC IdP,
  Patroni HA)   rate-lmt)  multi-Broker) models/docs)  embeddings)     realms)
     └──────────────┬──────────────────────────────────────────────┘
                    ▼
      ┌────────────────────────────┐
      │  Backup + DR               │
      │  • Backup server (minio →  │
      │     secondary S3 target)   │
      │  • pgBackRest / pg_dump    │
      │  • off-site vault          │
      │  • Tested restore drills   │
      └────────────────────────────┘

 Monitoring plane: Prometheus (metrics) + Grafana (UI) + Loki (logs) + Tempo (traces)
     ↓ eats from ServiceMonitors / scrape targets on every pod above
```

---

# 2. Technology → Artifact Matrix

| # | Technology    | Role                           | Artifact                                        |
|---|---------------|--------------------------------|--------------------------------------------------|
| 1 | Docker        | Single-host / small hospital   | `infrastructure/docker-compose.prod.yml`         |
| 2 | Kubernetes    | Medium + enterprise           | `infrastructure/kubernetes/**`                   |
| 3 | PostgreSQL 16 | System of record (per-svc DB) | `infrastructure/kubernetes/03-postgres.yaml`, helm deps |
| 4 | Redis 7       | Cache, rate limiting, pub/sub  | `infrastructure/kubernetes/04-redis.yaml`        |
| 5 | Kafka         | Event bus (KRaft, 3 brokers)   | `infrastructure/kubernetes/05-kafka.yaml`        |
| 6 | MinIO         | S3 object storage              | `infrastructure/kubernetes/06-minio.yaml`        |
| 7 | Qdrant        | Vector DB for RAG/knowledge    | `infrastructure/kubernetes/07-qdrant.yaml`       |
| 8 | Prometheus    | Metrics                        | `infrastructure/kubernetes/13-monitoring.yaml` + `monitoring/prometheus` |
| 9 | Grafana       | Dashboards/alerts              | `infrastructure/kubernetes/13-monitoring.yaml` + `monitoring/grafana` |
| 10 | Loki          | Centralized logs               | `infrastructure/kubernetes/13-monitoring.yaml` + `monitoring/loki` |
| 11 | Keycloak      | OIDC identity                  | `infrastructure/kubernetes/08-keycloak.yaml`     |
| 12 | NGINX         | Ingress controller             | `infrastructure/kubernetes/10-ingress.yaml`      |
| 13 | HAProxy       | Edge L4/L7 load balancer       | `infrastructure/kubernetes/12-haproxy.yaml`      |
| 14 | Cert Manager  | TLS certificates (Let's Encrypt/WACME) | `infrastructure/kubernetes/11-cert-manager.yaml` |
| 15 | GPU Server    | Local LLM inference (vLLM)     | `infrastructure/kubernetes/14-gpu.yaml`          |
| 16 | Backup Server | pgBackRest target, MinIO mirror| `infrastructure/backup/**`, `kubernetes/15-backup.yaml` |
| 17 | DR            | Cross-site restore             | `infrastructure/backup/DISASTER_RECOVERY.md`     |

Helm equivalent of all of the above: `infrastructure/helm/ehos-platform`.
CI/CD that provisions everything: `.github/workflows/deploy.yml`.

---

# 3. Service Registry (canonical names & ports)

| Service              | Port   | Namespace       | Notes                                   |
|----------------------|--------|-----------------|------------------------------------------|
| api-gateway          | 8000   | ehos-platform   | single entry for `/api`                  |
| configuration-service| 8100   | ehos-platform   | feature flags / reference config         |
| audit-service        | 8200   | ehos-platform   | immutable audit trail                    |
| notification-service | 8300   | ehos-platform   | SMS/Email/Push/In-app                    |
| authentication-service| 8500  | ehos-platform   | thin OIDC helper (Keycloak is IdP)       |
| keycloak             | 8400/8080 | ehos-platform | identity realm `ehos`                    |
| patient-service      | 8501   | ehos-clinical   | patient registry                        |
| ehr-service          | 8502   | ehos-clinical   | clinical chart / notes                   |
| knowledge-service    | 8505   | ehos-ai         | RAG knowledge base                       |
| ai-service           | 8506   | ehos-ai         | HospitalGPT gateway                      |
| prediction-service   | 8507   | ehos-ai         | forecasting/analytics                    |
| inference (vLLM)     | 8001   | ehos-ai         | GPU runtime                              |
| qdrant               | 6333   | ehos-ai         | vector store                             |
| postgres             | 5432   | dataplane (shared system db) | per-svc databases            |
| redis                | 6379   | dataplane       | cache / rate limit                       |
| kafka                | 9092   | dataplane       | event bus                                |
| minio                | 9000/9001 | dataplane  | S3 API + console                         |
| ehr-portal           | 5174   | ehos-clinical   | standalone SPA (served via nginx)        |
| patient-registration | 5173   | ehos-clinical   | standalone SPA                           |
| executive-dashboard  | 5176   | ehos-platform   | KPIs/forecasts/insights SPA              |
| ai-assistant         | 5175   | ehos-ai         | chat UI SPA                              |
| prometheus/grafana/loki/tempo | 9090/3000/3100/3200 | ehos-monitoring | observability |

---

# 4. Deployment Models

| Size               | Compute                     | Orchestration                    | Where                            |
|--------------------|-----------------------------|----------------------------------|----------------------------------|
| Clinic / small     | 1–2 hosts, 16–32 cores, 64–128 GB | `docker-compose.prod.yml`   | `infrastructure/`                |
| Medium hospital    | 3+ k8s nodes + 1 GPU node    | K8s YAML + Helm                  | `infrastructure/kubernetes+|helm` |
| Enterprise network | Multi-cluster + DR site     | Helm + GitOps + off-site DR      | see §5 & backup DR doc           |

---

# 5. Availability Targets

- Control plane: 3 nodes or managed k8s.
- Data plane: Postgres Patroni primary + 2 replicas; Kafka 3 brokers; MinIO
  distributed (4 drives); Redis master + 2 replicas (Sentinel optional).
- GPU node: dedicated `nodeSelector: nvidia.com/gpu` (NVIDIA device plugin).
- Ingress: HAProxy(2, keepalived VIP) → NGINX ingress(2 replicas).
- RPO / RTO: see `infrastructure/backup/BACKUP_STRATEGY.md` (§ objectives).

---

# 6. Security Posture

- TLS everywhere (cert-manager; internal mTLS via NetworkPolicy + Message-based
  auth where mandated by `SECURITY.md` / `AUTHENTICATION.md`).
- Secrets: Kubernetes `Secret` + optional external vault sync; **never** in manifests.
- NetworkPolicies (clusterscoped `default-deny`), service accounts with least
  privilege, image pull from private registry, Trivy scanning in CI.
- Keycloak realm `ehos` is the only identity source; services validate JWTs.
- GPU inference is LAN-only, never exposed via public ingress.

---

# 7. File Inventory

```
DEPLOYMENT_ARCHITECTURE.md        this document
infrastructure/docker-compose.prod.yml
infrastructure/docker-compose.prod.env.example
infrastructure/kubernetes/01..16-*.yaml
infrastructure/helm/ehos-platform/*
infrastructure/backup/*           backup + DR
monitoring/grafana/provisioning/  dashboards + datasources
monitoring/grafana/dashboards/ehos-overview.json
.github/workflows/deploy.yml
```

See `infrastructure/README.md` for the local **development** stack (that file
documents the dev-only compose); this blueprint is the **production** counterpart.

---

# 8. Final Principle

> Preserve in the operational blueprint the same property the clinical system
> depends on: fail, degrade and recover without human improvisation.