# P7-02 — Migrations, backup/restore, upgrades, worker, health

Status: accepted (P7 preview slice).

## Migrations

- Single linear head (currently `0014`). `alembic check`-style drift is
  covered by `test_migration_fresh_apply_and_rollback` + seed-count asserts.
- The app never migrates at startup (tested). Only explicit jobs migrate:
  `scripts/db-migrate.sh` (backup proof required via `BACKUP_REF`, single-head
  guard, current → review → upgrade → verify) or the preview `migrate`
  compose profile.
- `FORCE ROW LEVEL SECURITY` stays on (migration `0005`); seed roles (8) are
  re-verified after restore. Downgrades are never run blindly: irreversible
  migrations get a forward-fix; clinical/financial data is never destroyed by
  a rollback.

## Backup / restore

- Postgres custom-format dump + storage tarball, openssl-encrypted
  (`scripts/backup-preview.sh` / `restore-preview.sh`).
- RPO ≤ 24h / RTO ≤ 4h are *proposed targets*, not guarantees: no PITR or
  standby exists in the preview slice. Ownership: cloud/private = platform
  team; on-prem = customer (runbook provided).
- Restore is proven only by executing it into an isolated scratch database
  and checking table counts, seed roles, and RLS flags (script exits
  nonzero otherwise).

## Worker / health

- Liveness (`/api/healthz`): process alive. No dependency checks by design.
- Readiness (`/api/readyz`): 200 `ready` only when the app-role DB answers
  `SELECT 1`; else 503 with coarse reason codes (`db-not-configured` /
  `db-unreachable`). No internals leak.
- Worker health: boot validation (`require_valid_for_boot`) + `worker --once`
  for gates + `ops check-readiness` (config, DB round-trip, storage probe
  round-trip, notify provider status). Outbox dead-letter counts remain the
  operational signal for repeated delivery failure.
