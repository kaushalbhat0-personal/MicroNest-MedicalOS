# Migration Rules (P1, locked)

- Fresh history from `0001_identity`. Legacy chains are frozen reference only.
- Migrations are explicit jobs (alembic CLI / CI / release pipeline).
  The app NEVER migrates at startup (deployment test asserts the absence).
- Linear, reviewed, forward-only; `downgrade()` maintained and exercised by
  `test_migration_fresh_apply_and_rollback` (fresh apply + downgrade + re-apply).
- Seeds in migrations: permission bundles ONLY (reference data). Never tenant,
  user, or business data. Never secrets (roles created NOLOGIN; passwords set
  by ops/secret-manager outside history).
- No `sa.inspect()` in migrations (breaks offline SQL); no data backfills
  without dry-run + review.
