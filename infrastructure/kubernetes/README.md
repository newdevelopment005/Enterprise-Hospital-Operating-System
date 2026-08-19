# Kubernetes
# Kubernetes manifests for the EHOS production platform (medium/enterprise model).

Prerequisites: a Kubernetes cluster, an ingress controller, cert-manager, and the
data-plane storage class (`ehos-fast`, see `02-storageclass.yaml`). For HA data
plane in production prefer the operator-based Helm charts referenced in
`../helm/ehos-platform/Chart.yaml` (Patroni/CloudNativePG, Kafka KRaft chart,
Redis Sentinel, distributed MinIO).

## Apply order

```bash
kubectl apply -f 00-namespaces.yaml
kubectl apply -f 01-secrets.example.yaml        # replace with real sealed secrets
kubectl apply -f 02-storageclass.yaml
kubectl apply -f 03-postgres.yaml
kubectl apply -f 04-redis.yaml
kubectl apply -f 05-kafka.yaml
kubectl apply -f 06-minio.yaml
kubectl apply -f 07-qdrant.yaml
kubectl apply -f 08-keycloak.yaml
kubectl apply -f 09-app-services.yaml           # envsubst REGISTRY/TAG first
kubectl apply -f 09b-frontend.yaml              # envsubst REGISTRY/TAG first
kubectl apply -f 10-ingress.yaml
kubectl apply -f 11-cert-manager.yaml
kubectl apply -f 12-haproxy.yaml
kubectl apply -f 13-monitoring.yaml
kubectl apply -f 14-gpu.yaml
kubectl apply -f 15-backup.yaml
kubectl apply -f 16-network-policies.yaml
```

`09*` manifests contain `${REGISTRY}` / `${TAG}` placeholders:

```bash
export REGISTRY=ghcr.io/your-org/ehos TAG=0.3.0
envsubst < 09-app-services.yaml | kubectl apply -f -
```

## Layout

| File | Provides |
|---|---|
| 00 | namespaces (platform / clinical / ai / data / monitoring / backup) |
| 01 | secret templates (never prod credentials) |
| 02 | fast storage class |
| 03–08 | data plane: postgres, redis, kafka (KRaft), minio (distributed), qdrant, keycloak |
| 09/09b | backend Deployments+Services+HPA, frontend SPAs |
| 10 | NGINX ingress classes + routes |
| 11 | cert-manager ACME Issuers + `ehos-tls` certificate |
| 12 | HAProxy edge DaemonSet |
| 13 | prometheus / grafana / loki |
| 14 | GPU inference (vLLM) + dcgm-exporter |
| 15 | backup CronJobs (pg_dump, S3 mirror, qdrant snapshots) |
| 16 | zero-trust NetworkPolicies |

Most components are also packaged as Helm (see `../helm`); prefer the chart for
repeatable environments (dev/uat/prod).