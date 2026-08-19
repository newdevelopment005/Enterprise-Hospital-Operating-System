# EHOS Disaster Recovery Plan

**Owner:** Infrastructure / Hospital IT
**Related:** DEPLOYMENT.md §16, BACKUP_STRATEGY.md

## 1. Goals

- Restore the full platform in a DR site within **RTO ≤ 4 h**.
- Lose at most **RPO ≤ 15 min** of committed clinical/audit data.
- Annual DR test with written evidence (mandated by DEVOPS_CICD §25).

## 2. Threats covered

| Scenario | Impact | Response |
|---|---|---|
| Data-centre loss | total | DR site activate (below) |
| Host failure (k8s node) | partial | k8s reschedules; data plane self-heals (Patroni/Kafka quorum) |
| Database corruption | data | point-in-time restore from WAL archive |
| Ransomware | all | wipe + restore from tertiary/off-site copy (encrypted) |
| Internet outage | — | local-first: platform continues (only IdP/LLM features degrade) |

## 3. DR site topology

```
Primary site                    DR site
  k8s cluster                    k8s cluster (warm standby)
    data plane                     data plane
    backup server  ──replicate──▶  backup target (S3, off-site)
                                   + vault (age-encrypted secrets, model hashes)
```

- DR cluster is kept warm: same Helm chart + values, same image tags pinned.
- Data replication: nightly full (CronJob `mirror-to-backup-server`) + continuous
  Postgres WAL streaming to the DR bucket.
- Secrets: Sealed Secrets / SOPS with the decrypt key stored in the DR vault.

## 4. Activation runbook (primary loss)

1. `kubectl --context=dr create namespace ehos-platform ...` (or GitOps reconcile).
2. Restore secrets: SOPS/sealed secrets decrypt into `ehos-backup` namespace.
3. Restore data: `kubectl apply -f infrastructure/kubernetes/15-backup.yaml`,
   then `kubectl create job --from=cronjob/postgres-backup restore-dr` with
   `restore.sh --latest`.
4. Point DNS / HAProxy VIP at the DR ingress.
5. Verify: `/api/health`, Keycloak realm reachable, one read + one write smoke test.
6. Declare recovery complete; open incident record in the audit trail.

## 5. Recovery order

1. PostgreSQL (system of record) → 2. MinIO + Qdrant (objects/vectors)
3. Kafka (event replay) → 4. services (helm, idempotent) → 5. frontends/ingress
6. monitoring → 7. smoke tests.

## 6. Testing

- **Monthly**: restore drill in staging/DR using the newest backup.
- **Quarterly**: full failover test including DNS/VIP switch.
- Every drill records: timestamps, restored data checksums, `pg_restore --list`,
  and a signed pass/fail note in the changelog.

## 7. Metrics to track

| Metric | Target |
|---|---|
| DR activation time | ≤ 4 h |
| Restore point freshness | ≤ 15 min |
| % backups verified | 100% monthly |
| Successful restores / attempts | 100% |

## 8. Forbidden

❌ Activate DR before the primary is safely isolated (avoid write split-brain)
❌ Skip the restore drill because "nothing has happened yet"
❌ Store the DR decryption key on the same cluster it decrypts