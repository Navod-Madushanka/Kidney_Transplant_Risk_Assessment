#!/usr/bin/env bash
# scripts/backup_db.sh
#
# Postgres backup for the production deployment (B-none-specific / Phase
# 3.7 of FINALIZATION-PLAN.md). Dumps the postgres service defined in
# docker-compose.prod.yml to a timestamped, custom-format (-Fc) file on
# local disk, and prunes dumps older than RETENTION_DAYS.
#
# -Fc (custom format), not plain SQL: it's compressed, and pg_restore can
# select individual tables/schemas out of it or parallelize the restore
# (-j) -- a plain `pg_dump > file.sql` can't do either. See
# scripts/restore_db.sh for the matching restore side.
#
# Usage (from the repo root, where docker-compose.prod.yml lives):
#   ./scripts/backup_db.sh
#
# Intended to run from cron, e.g. nightly at 02:00:
#   0 2 * * * cd /path/to/repo && ./scripts/backup_db.sh >> /var/log/kidney-backup.log 2>&1
#
# Reads POSTGRES_USER/POSTGRES_DB from .env (same file docker compose
# itself reads) so this never needs its own separate copy of those values
# to drift out of sync with the running database.
#
# BACKUP_DIR and RETENTION_DAYS are placeholders (local disk only) --
# see docs/backup-runbook.md for why, and what changes when the hospital's
# actual retention/offsite policy is decided.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/kidney-transplant}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

if [ ! -f .env ]; then
  echo "backup_db.sh: .env not found at $REPO_ROOT/.env -- copy .env.example and fill it in first." >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a; source .env; set +a

: "${POSTGRES_USER:?POSTGRES_USER must be set in .env}"
: "${POSTGRES_DB:?POSTGRES_DB must be set in .env}"

mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DUMP_FILE="$BACKUP_DIR/kidney-transplant-${TIMESTAMP}.dump"
TMP_FILE="${DUMP_FILE}.in-progress"

echo "backup_db.sh: dumping ${POSTGRES_DB} -> ${DUMP_FILE}"

# Dumps inside the container to a scratch path, then copies out -- avoids
# needing the `postgres` client tools installed on the host at all, only
# `docker compose` and `docker cp`. Writes to a .in-progress name first and
# renames on success, so a backup that dies partway through (disk full,
# container restart mid-dump) never gets mistaken for a complete one by
# whatever picks the newest file at restore time.
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/kidney-transplant-backup.dump

docker compose -f docker-compose.prod.yml cp \
  postgres:/tmp/kidney-transplant-backup.dump "$TMP_FILE"

docker compose -f docker-compose.prod.yml exec -T postgres \
  rm -f /tmp/kidney-transplant-backup.dump

mv "$TMP_FILE" "$DUMP_FILE"
echo "backup_db.sh: wrote $(du -h "$DUMP_FILE" | cut -f1) to $DUMP_FILE"

# Retention: delete dumps older than RETENTION_DAYS. Only ever touches
# files matching this script's own naming pattern, in BACKUP_DIR
# specifically -- never a bare `find $BACKUP_DIR -mtime ... -delete`
# without both of those scoped, in case something else ever shares the
# directory.
DELETED_COUNT=$(find "$BACKUP_DIR" -maxdepth 1 -name 'kidney-transplant-*.dump' -mtime "+${RETENTION_DAYS}" -print -delete | wc -l)
if [ "$DELETED_COUNT" -gt 0 ]; then
  echo "backup_db.sh: pruned $DELETED_COUNT dump(s) older than ${RETENTION_DAYS} days"
fi
