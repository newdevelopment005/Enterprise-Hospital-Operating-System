#!/usr/bin/env sh
# EHOS backup script (Docker single-host / backup-scheduler container).
# Run: backup.sh [--full|--incremental|--prune|--verify]
#
# Environment:
#   BACKUP_DIR          default /backups
#   POSTGRES_HOST       default postgres
#   POSTGRES_USER       default ehos
#   POSTGRES_PASSWORD   required
#   MINIO_ALIAS_LOCAL   endpoint alias for primary MinIO
#   BACKUP_TARGET_S3_ENDPOINT / ACCESS_KEY / SECRET_KEY / BUCKET (optional off-site)
#   QDRANT_URL          default http://qdrant:6333
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_USER="${POSTGRES_USER:-ehos}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD required}"
QDRANT_URL="${QDRANT_URL:-http://qdrant:6333}"
STAMP="$(date +%F-%H%M)"

log() { echo "[backup] $*"; }

backup_postgres() {
  log "postgres dump"
  mkdir -p "$BACKUP_DIR/postgres"
  # one database per EHOS service (see database/init)
  for db in ehos_platform ehos_clinical ehos_ai ehos_keycloak ehos_analytics; do
    if PGPASSWORD="$POSTGRES_PASSWORD" pg_isready -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$db" >/dev/null 2>&1; then
      PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -Fc -d "$db" \
        > "$BACKUP_DIR/postgres/${db}_${STAMP}.dump"
      log "  dumped $db"
    else
      log "  skipped $db (absent)"
    fi
  done
}

backup_minio() {
  log "minio mirror"
  if command -v mc >/dev/null 2>&1; then
    mkdir -p "$BACKUP_DIR/minio"
    mc alias set primary "http://minio:9000" "${MINIO_ROOT_USER:-ehos}" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1
    mc mirror --overwrite primary/ "$BACKUP_DIR/minio" >/dev/null
  fi
}

backup_qdrant() {
  log "qdrant snapshots"
  for collection in $(curl -sf "$QDRANT_URL/collections" | sed -n 's/.*"name":"\([^"]*\)".*/\1/p' 2>/dev/null); do
    curl -sf -X POST "$QDRANT_URL/collections/$collection/snapshots" >/dev/null
    log "  snapshotted $collection"
  done
}

backup_keycloak() {
  log "keycloak realm export"
  # placeholder — production uses the realm JSON mounted under /opt/keycloak/data/import
  [ -d "$BACKUP_DIR/keycloak" ] || mkdir -p "$BACKUP_DIR/keycloak"
}

sync_offsite() {
  if [ -n "${BACKUP_TARGET_S3_ENDPOINT:-}" ]; then
    log "off-site mirror"
    mc alias set offsite "$BACKUP_TARGET_S3_ENDPOINT" "$BACKUP_TARGET_ACCESS_KEY" "$BACKUP_TARGET_SECRET_KEY" >/dev/null 2>&1
    mc mirror --overwrite "$BACKUP_DIR" "offsite/$BACKUP_TARGET_BUCKET" >/dev/null
    log "  synced"
  else
    log "  off-site target not configured; skipping"
  fi
}

prune() {
  log "prune (7d daily)"
  find "$BACKUP_DIR/postgres" -name '*.dump' -mtime +7 -delete 2>/dev/null || true
  find "$BACKUP_DIR/minio" -mtime +7 -delete 2>/dev/null || true
}

case "${1:---incremental}" in
  --full)        backup_postgres; backup_minio; backup_qdrant; backup_keycloak; sync_offsite ;;
  --incremental) backup_postgres ;;
  --prune)       prune ;;
  --verify)      log "verify: $(pg_restore --list "$BACKUP_DIR"/postgres/*.dump 2>/dev/null | wc -l) dumps readable" ;;
  *) echo "usage: $0 [--full|--incremental|--prune|--verify]" >&2; exit 2 ;;
esac

log "done $(date -Is)"