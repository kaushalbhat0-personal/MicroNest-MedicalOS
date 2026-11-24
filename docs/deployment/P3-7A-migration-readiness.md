# P3.7A — Alembic Migration Readiness (→ 0027)

**Date:** 2026-11-24  
**Target DB:** Supabase staging `postgres` (empty before upgrade)  
**Migrator role:** `hos_owner` via session pooler

## Chain

- Files: **27**  
- Root: `0001_identity`  
- Head: `0027_saas_payment_reliability`  
- Linear chain verified (ordered_count=27)

## Review notes

| Topic | Finding |
|-------|---------|
| Extensions in migrations | None call `CREATE EXTENSION` (Supabase already has `pgcrypto`, `uuid-ossp`, etc.) |
| `gen_random_uuid()` | Used in seeds; available on PG17 / pgcrypto |
| Role creation | `0005_rls` creates `hos_app` if missing (NOLOGIN); cloud role already existed as LOGIN — DO block no-op |
| Grants | Repeated `GRANT … TO hos_app` across clinical/billing/inventory/saas revisions |
| RLS | `ENABLE` + `FORCE` on tenant tables; policies `TO hos_app` |
| DROP usage | Present mainly in downgrade paths / policy rebuilds — upgrade path reviewed as additive |
| Destructive reset | **Not performed** |
| Downgrade | Not executed |

## Pre-flight

| Check | Result |
|-------|--------|
| Public base tables before | **0** |
| Alembic table before | Absent |
| Safe to upgrade empty staging | **Yes** |

## Applied result

| Check | Result |
|-------|--------|
| `alembic upgrade head` | **Exit 0** |
| `alembic_version` | `0027_saas_payment_reliability` |
| Public tables | **75** |
| Key tables present | tenants, users, patients, document_references, consents, saas_payment_transactions |
| RLS-enabled tables | **57** |

## Local database

Local PostgreSQL 19 / `healthcare_os` was **not** migrated or modified by this phase. Cloud-only `OWNER_DATABASE_URL` override was process-scoped.
