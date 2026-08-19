#!/usr/bin/env sh
# EHOS restore script — run on a fresh host/cluster.
# Restores postgres, minio and qdrant from the newest backup in BACKUP_DIR.
# Usage: restore.sh [--latest|--file /path/backup.dump] [--minio] [--qdrant]
#
# Environment:
#   BACKUP_DIR / POSTGRES_HOST / POSTGRES_USER / POSTGRES_PASSWORD (same as backup.sh)
#   MINIO_ROOT_USER / MINIO_ROOT_PASSWORD
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_USER="${POSTGRES_USER:-ehos}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD required}"

log() { echo "[restore] $*"; }

latest() { ls -1t "$BACKUP_DIR"/postgres/*.dump 2>/dev/null | head -n1; }

restore_postgres() {
  local file
  file="${1:-$(latest)}"
  [ -n "$file" ] || { log "no postgres backup found"; exit 1; }
  local db
  db="$(basename "$file" .dump | sed 's/_[0-9-]*$//')"
  log "restoring $db from $file"
  # recreate target database (services re-run migrations afterwards via `make migrate`)
  PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d postgres \
    -c "DROP DATABASE IF EXISTS $db WITH (FORCE);" -c "CREATE DATABASE $db;"
  PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$db" --no-owner --role="$POSTGRES_USER" "$file"
  log "  restored $db"
}

restore_minio() {
  log "minio restore (mirror back)"
  mc alias set primary "http://minio:9000" "${MINIO_ROOT_USER:-ehos}" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1
  mc mirror --overwrite "$BACKUP_DIR/minio" primary/ >/dev/null
  log "  minio restored"
}

restore_qdrant() {
  log "qdrant restore — upload snapshots then call /collections/{c}/snapshots/{s}/recover"
  # Snapshots are taken on the qdrant node; recover via its HTTP API. Intentionally
  # left for the operator: exact recovery requires the qdrant node reachable here.
  log "  manual step: see BACKUP_STRATEGY.md runbook"
}

case "${1:---latest}" in
  --latest) restore_postgres "$(latest)" ;;
  --file)   restore_postgres "$2" ;;
  --minio)  restore_minio ;;
  --qdrant) restore_qdrant ;;
  *) echo "usage: $0 [--latest|--file F|--minio|--qdrant]" >&2; exit 2 ;;
esac

log "restore complete — run migrations: make migrate (or helm hook) then smoke-test /health"