# EHOS Monitoring baseline (Phase 0)

Prometheus (metrics), Grafana (dashboards), Loki (logs), Tempo (traces).

## Components

| Component | Purpose | Image |
|---|---|---|
| Prometheus | Scrape service metrics | prom/prometheus |
| Grafana | Dashboards + alerting UI | grafana/grafana |
| Loki | Aggregated structured JSON logs | grafana/loki |
| Tempo | Distributed tracing (OTLP ingest) | grafana/tempo |

## Adding a service

1. Export metrics at `/metrics`.
2. Add the host:port to `prometheus/prometheus.yml` under `ehos-services`.
3. Emit structured JSON logs to stdout (`CODING_STANDARDS.md` section 14) for Loki to collect.
4. Add trace spans following the OTLP protocol for Tempo.

## Running with the compose stack

Monitoring services are defined in the root compose file under the `monitoring`
profile:

```bash
docker compose --profile monitoring up -d
```

| UI | URL |
|---|---|
| Grafana | http://localhost:3000 (admin/admin) |
| Prometheus | http://localhost:9090 |