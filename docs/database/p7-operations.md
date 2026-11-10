# P7 operations: migrate, back up, restore, upgrade

## Migration procedure

1. **Backup.** Take and record a backup (`scripts/backup-preview.sh` for
   preview; managed PITR snapshot or the same scripts for private/on-prem).
   Record its reference as `BACKUP_REF`.
2. **Verify current head.** `alembic -c backend/alembic.ini current` and
   `heads` — there must be exactly one head.
3. **Review.** `alembic -c backend/alembic.ini history -r current:head`;
   read the pending migration (data migrations need extra scrutiny).
4. **Apply.** `BACKUP_REF=... OWNER_DATABASE_URL=... scripts/db-migrate.sh`
   (or the preview `migrate` compose profile).
5. **Verify.** Single head, `SELECT count(*) FROM roles WHERE tenant_id IS
   NULL` returns 8, RLS-enabled tables ≥ 6, app boots, `/api/readyz` is 200.
6. **Smoke.** Backend suite + `scripts/preview-smoke.sh` (preview).
7. **Record.** Deployment version = migration head + image tags.

## Rollback policy

- Reversible migrations: `alembic downgrade -1` only after a fresh backup
  and only when no clinical/financial rows were written under the new schema.
- Irreversible migrations: forward-fix only. Never downgrade blindly across
  a migration that touched clinical or billing tables.

## Backup / restore

- Preview: `scripts/backup-preview.sh` (encrypted dump + storage tarball),
  `scripts/restore-preview.sh` (restores into an isolated `restore_check_*`
  database, verifies counts/seeds/RLS, drops it).
- RPO ≤ 24h / RTO ≤ 4h are proposed targets. Achieving them needs scheduled
  backups + measured restores (post-P7).
- Ownership: cloud/private = platform team; on-prem = customer.

## External prerequisites (not provisioned by P7)

DNS + TLS certificates, managed Postgres, S3 bucket, SES/SMS provider
account, secret manager, container registry. The preview slice validates
everything else locally so provisioning later is configuration, not code.
