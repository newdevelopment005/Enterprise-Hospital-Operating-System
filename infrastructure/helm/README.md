# ehos-platform
# EHOS umbrella Helm chart: application services + data plane dependencies.

## Add repos & package

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add minio https://charts.min.io/
helm repo add qdrant https://qdrant.github.io/helm-charts
helm repo add codecentric https://codecentric.github.io/helm-charts
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo add jetstack https://charts.jetstack.io
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm dependency update infrastructure/helm/ehos-platform
```

## Deploy (dev)

```bash
helm upgrade --install ehos infrastructure/helm/ehos-platform \
  --namespace ehos-platform --create-namespace
```

## Deploy (production)

```bash
helm upgrade --install ehos infrastructure/helm/ehos-platform \
  -f infrastructure/helm/ehos-platform/values.yaml \
  -f infrastructure/helm/ehos-platform/values-prod.yaml \
  --namespace ehos-platform --create-namespace --atomic
```

## Render without installing

```bash
helm template ehos infrastructure/helm/ehos-platform -f .../values-prod.yaml
```

## Layout

| Path | Purpose |
|---|---|
| `Chart.yaml` | umbrella + pinned external dependencies (data plane, identity, edge, monitoring) |
| `values.yaml` | defaults for the EHOS application services |
| `values-prod.yaml` | production overrides (HA, sizing, SASL, persistence) |
| `templates/deployment.yaml` | Deployment per `values.services` entry |
| `templates/service.yaml` | Service per service |
| `templates/hpa.yaml` | HPA per service (when `hpa` set) |
| `templates/frontend.yaml` | SPA Deployments + Services |
| `templates/ingress.yaml` | NGINX ingress routes |
| `templates/servicemonitor.yaml` | monitoring ServiceMonitors |
| `templates/networkpolicy.yaml` | zero-trust default-deny |
| `templates/namespaces.yaml` | EHOS namespaces |