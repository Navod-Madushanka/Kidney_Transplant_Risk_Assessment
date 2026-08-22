# Backup and restore runbook

Phase 3.7 of `FINALIZATION-PLAN.md`. Covers the production Postgres database
(`docker-compose.prod.yml`'s `postgres` service) — the only stateful piece of
this system that isn't otherwise reproducible (`kidney-backend/uploads/` is
also stateful and NOT covered here yet; see "Not yet covered" below).

## What's implemented

- **`scripts/backup_db.sh`** — dumps the database (`pg_dump -Fc`, custom
  format: compressed, supports selective/parallel restore) to a timestamped
  file under `BACKUP_DIR` (default `/var/backups/kidney-transplant`), then
  prunes dumps older than `RETENTION_DAYS` (default 30). Reads
  `POSTGRES_USER`/`POSTGRES_DB` from the repo's `.env`, so it can never drift
  out of sync with whatever the running stack actually uses.
- **`scripts/restore_db.sh`** — restores a dump produced by the above back
  into the running `postgres` service. Refuses to run against a database
  that already has tables unless passed `--force`, since a restore is the
  one operation here that can clobber real data if pointed at the wrong
  target.

Both scripts talk to the database exclusively through
`docker compose -f docker-compose.prod.yml exec/cp postgres ...` — nothing
needs the `postgres` client tools installed on the host itself, only Docker
Compose.

## Destination: local disk only, for now

`BACKUP_DIR` is a local directory on the same host running the stack. That
means a backup survives an accidental `DROP TABLE`, a bad migration, or
Postgres itself getting corrupted — **it does not survive that host's disk
failing, being stolen, or the building it's in burning down.** For a real
hospital pilot handling real patient data, an offsite (or at least
off-host) copy is the actual requirement, not a nice-to-have.

This was deliberately scoped to local-disk-only for this pass because the
actual destination (a network share, encrypted cloud storage, another
server, tape — whatever the hospital's IT policy already uses for this)
is not something this repo can decide unilaterally. **Before the pilot
goes live, `scripts/backup_db.sh`'s output needs to be copied off-host on
the same schedule it's produced** — the simplest addition is a second
cron line (`rsync`/`rclone`/whatever fits the hospital's existing infra)
pointed at `BACKUP_DIR` after each run; nothing about the dump format
constrains that choice.

## Retention: 30 days, a starting recommendation

`RETENTION_DAYS=30` is a reasonable-but-arbitrary default, not a clinical
or legal determination. Real retention requirements for patient health
data are typically set by hospital policy or local law, not by whoever
wrote the backup script — **treat this the same as the clinical constants
in `FINALIZATION-PLAN.md`'s guardrails: don't treat 30 days as final
without the hospital's own retention policy confirming it.**

## Cron setup

```cron
# /etc/cron.d/kidney-transplant-backup, or `crontab -e` as whichever user
# has docker compose access to the running stack.
0 2 * * * cd /path/to/repo && ./scripts/backup_db.sh >> /var/log/kidney-backup.log 2>&1
```

## Restore procedure

```bash
# 1. Find the dump to restore from.
ls -la /var/backups/kidney-transplant/

# 2. Restore it. Prompts for confirmation if the target database already
#    has tables (pass --force to skip that, e.g. scripted DR where you've
#    already confirmed the target is meant to be overwritten).
./scripts/restore_db.sh /var/backups/kidney-transplant/kidney-transplant-<timestamp>.dump

# 3. Verify (the script prints this command at the end too).
docker compose -f docker-compose.prod.yml exec postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\dt'
```

Restoring into a **fresh** database (the normal DR scenario — the old one
is gone or corrupted) needs no `--force`: an empty database has zero
tables, so the confirmation gate never triggers.

## Restore drill — actually performed, 2026-08-22

Per Phase 6.2's "a real restore from backup into a clean database," this
was run for real, not just written down. Against a disposable Postgres 16
database (not the app's real dev/test databases — a throwaway one created
and dropped specifically for this drill) using the exact same `pg_dump -Fc`
/ `pg_restore` commands the scripts above wrap:

1. Created `backup_drill` with one table, 3 seeded rows.
2. `pg_dump -Fc` to a file, copied out of the container to the host.
3. **Dropped `backup_drill` entirely** (simulating the actual disaster this
   exists to recover from) and recreated it empty.
4. `pg_restore` the dump file back in.
5. Verified: all 3 rows present, byte-for-byte matching content and
   original timestamps.

```
 id |     full_name      |          created_at
----+--------------------+-------------------------------
  1 | Test Patient One   | 2026-08-22 05:39:54.364327+00
  2 | Test Patient Two   | 2026-08-22 05:39:54.364327+00
  3 | Test Patient Three | 2026-08-22 05:39:54.364327+00
(3 rows)
```

This confirms the underlying `pg_dump -Fc` / `pg_restore` mechanics work
end-to-end against Postgres 16 (the version this stack actually runs). It
does **not** by itself confirm `scripts/backup_db.sh`/`restore_db.sh`'s
`docker compose exec/cp` plumbing against a real `docker-compose.prod.yml`
deployment (that needs a running production-shaped stack, which wasn't
stood up for this drill) — re-run the drill against the real compose stack
once it exists, before relying on this for a real incident.

## Not yet covered

- **Offsite/off-host copy** — see above.
- **`kidney-backend/uploads/`** (the `backend-uploads` volume: report-file
  attachments and the OCR upload spool) is not included in
  `scripts/backup_db.sh` at all. A restored database would reference
  report files that no longer exist on disk if this volume is lost
  separately from Postgres. Back it up (e.g. `docker run --rm -v
  kidney-transplant-prod_backend-uploads:/data -v
  "$BACKUP_DIR":/backup alpine tar czf
  /backup/uploads-<timestamp>.tar.gz -C /data .`) on the same schedule and
  with the same offsite-copy requirement as the database dump.
- **Automated restore testing** — this drill was done by hand. A pilot
  running for months should re-verify restore works on a recurring
  schedule (quarterly is a common baseline), not rely on one manual proof
  from before launch.
