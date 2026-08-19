# EHOS Backup Strategy

**Owner:** Infrastructure / Hospital IT
**Related:** DEPLOYMENT.md §14–16, DEPLOYMENT_ARCHITECTURE.md §2

## 1. Objective & targets

| Metric | Target |
|---|---|
| RPO (point-in-time loss) | ≤ 15 min (Postgres WAL), 24h for fulls |
| RTO (restore of whole platform) | ≤ 4 h (K8s), ≤ 2 h (single host) |
| Retention | 7 daily · 4 weekly · 12 monthly · 1 yearly vault |

Backups follow the **3-2-1 rule**: 3 copies, 2 media (disk + off-line), 1 off-site.

## 2. What is backed up

| Component | Method | Frequency |
|---|---|---|
| PostgreSQL (all ehos_* DBs + Keycloak DB) | `pg_dump -Fc` full + WAL archiving | daily full, continuous WAL |
| Kafka topics | mirror (Kafka MirrorMaker / partition replication to backup cluster) | daily |
| MinIO buckets | `mc mirror` to backup S3 target | nightly |
| Qdrant collections | HTTP snapshots | nightly |
| Keycloak realm export | realm JSON export | nightly |
| Kubernetes state | manifest backup (helm releases, Secrets encrypted w/ age) | nightly |
| AI models | filesystem copy (models immutable, checksummed) | on release |

## 3. Destinations

1. **Primary**: local cluster PVC / backup server (`/backups`).
2. **Secondary**: MinIO/bucket `ehos-backups` on the backup server (separate host).
3. **Tertiary (off-site)**: DR site bucket / removable media, replicated nightly.

## 4. Execution

- **Docker (single host):** `infrastructure/backup/backup.sh` via the
  `backup-scheduler` container in `docker-compose.prod.yml` (hourly incremental,
  nightly full).
- **Kubernetes:** CronJobs in `infrastructure/kubernetes/15-backup.yaml` and
  `infrastructure/helm/ehos-platform` (postgres-backup, mirror-to-backup-server,
  qdrant-snapshot). WAL archiving via Patroni/CloudNativePG when HA is enabled.

## 5. Retention & cleanup

```text
daily   → keep 7        (ehos_platform_YYYY-MM-DD.dump)
weekly  → keep 4        (dow-1, oldest overwritten)
monthly → keep 12       (first-of-month)
yearly  → keep 1        (cold storage / DR vault)
```

Cleanup is performed by `backup.sh --prune` (find -mtime / age-based).

## 6. Verification (mandatory)

- Every backup run writes a `VERIFY.md` marker: `pg_restore --list`, `mc stat`,
  `md5sum` for model files.
- **Monthly restore drill** in the DR environment (see DISASTER_RECOVERY.md).
- Monitoring alert `EHOSBackupMissing` fires if no fresh backup for 26 h
  (prometheus rule in `infrastructure/kubernetes/13-monitoring.yaml`).

## 7. Runbooks

| Situation | Action |
|---|---|
| Full restore | `restore.sh --latest` on a fresh host, then run `make migrate` |
| Point-in-time | `restore.sh --pitr <timestamp>` (needs WAL archive) |
| Data-plane loss | restore postgres + redis; replay Kafka (offline-first services rebuild) |
| Ransomware incident | restore from Tertiary/off-site copy; do not touch primary |

## 8. Forbidden

❌ Delete backups without approval
❌ Keep only one copy
❌ Test restore only "when something breaks"
❌ Store plaintext secrets inside backups (encrypt with age; key in DR vault)