#!/usr/bin/env bash
# scripts/restore_db.sh
#
# Restores a dump produced by scripts/backup_db.sh into the running
# postgres service (docker-compose.prod.yml). See docs/backup-runbook.md
# for the full drill this was validated against and the "why" behind each
# step -- this script is deliberately conservative (asks for confirmation,
# refuses to run against a database with existing tables without --force)
# since a restore is the one operation here that can destroy current data
# if pointed at the wrong target.
#
# Usage (from the repo root):
#   ./scripts/restore_db.sh /var/backups/kidney-transplant/kidney-transplant-20260822T020000Z.dump
#   ./scripts/restore_db.sh --force /path/to/dump.dump   # skip the confirmation prompt (e.g. scripted DR)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

FORCE=0
if [ "${1:-}" = "--force" ]; then
  FORCE=1
  shift
fi

DUMP_FILE="${1:-}"
if [ -z "$DUMP_FILE" ]; then
  echo "Usage: $0 [--force] <path-to-dump-file>" >&2
  exit 1
fi
if [ ! -f "$DUMP_FILE" ]; then
  echo "restore_db.sh: no such file: $DUMP_FILE" >&2
  exit 1
fi

if [ ! -f .env ]; then
  echo "restore_db.sh: .env not found at $REPO_ROOT/.env" >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a; source .env; set +a

: "${POSTGRES_USER:?POSTGRES_USER must be set in .env}"
: "${POSTGRES_DB:?POSTGRES_DB must be set in .env}"

EXISTING_TABLES=$(docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")

if [ "$EXISTING_TABLES" -gt 0 ] && [ "$FORCE" -ne 1 ]; then
  echo "restore_db.sh: ${POSTGRES_DB} already has ${EXISTING_TABLES} table(s)."
  echo "pg_restore below runs without --clean, so this ADDS to what's there and will"
  echo "fail loudly on any conflicting row/constraint rather than silently overwrite --"
  echo "but restoring into a database that already has real data is almost never what"
  echo "you actually want. Re-run with --force to proceed anyway, or restore into a"
  echo "fresh database instead."
  exit 1
fi

echo "restore_db.sh: restoring $DUMP_FILE into ${POSTGRES_DB}"

docker compose -f docker-compose.prod.yml cp "$DUMP_FILE" postgres:/tmp/kidney-transplant-restore.dump

# -1 (single transaction): the whole restore commits or rolls back
# together -- no partial schema left behind on a mid-restore failure.
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" -1 /tmp/kidney-transplant-restore.dump

docker compose -f docker-compose.prod.yml exec -T postgres \
  rm -f /tmp/kidney-transplant-restore.dump

echo "restore_db.sh: done. Verify with:"
echo "  docker compose -f docker-compose.prod.yml exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -c '\\dt'"
