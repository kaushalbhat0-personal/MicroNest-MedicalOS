# P3.7A — Supabase Staging Setup Report

**Date:** 2026-11-24  
**Scope:** Supabase only (Vercel/Render deferred)  
**Data:** Synthetic only — no real PHI  
**Git:** No commit; local `.env` not staged

## Verdict: **CONDITIONAL PASS**

Dedicated Supabase project verified, `hos_owner` / `hos_app` created, Alembic **0027** applied on an empty staging database, private Storage drill exercised against the **real** S3-compatible endpoint. Remaining gaps: Render mapping secrets incomplete, `hos_owner` lacks local-parity `BYPASSRLS` (documented), shared S3 credential is account/bucket-scoped (not per-tenant IAM).

## 1. Project verification

| Field | Value |
|-------|-------|
| Project ref | `dimhmkfiqdlpxiafqnxl` |
| Name | `MicroNest-MedicalOS` |
| Region | `eu-west-3` |
| Status | `ACTIVE_HEALTHY` |
| Accessible projects for PAT | **1** (this project only) |
| Postgres | 17.11 |
| Confidence | High — sole accessible project; product-named |

Note: name does not include the word “staging”; identity is the dedicated MicroNest Medical OS project.

## 2. Environment audit (names only — no values)

| Variable | Status | Role |
|----------|--------|------|
| `SUPABASE_PROJECT_REF` | Present (normalized to ref id) | Project id |
| `SUPABASE_URL` | Present | API URL |
| `SUPABASE_ACCESS_TOKEN` | Present | **Management PAT** (`sbp_*`) — not S3 |
| `OWNER_DATABASE_URL_CLOUD` | Present | Session pooler `hos_owner.<ref>` + `sslmode=require` |
| `APP_DATABASE_URL_CLOUD` | Present | Session pooler `hos_app.<ref>` + `sslmode=require` |
| `APP_ROLE_PASSWORD_CLOUD` | Present | Role login secret |
| `S3_ENDPOINT_URL` | Present | Supabase Storage S3 API |
| `S3_BUCKET` | Present (`dental-os`) | Existing private bucket |
| `S3_REGION` | Present (`eu-west-3`) | |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | Present | **S3 protocol credentials** (opaque) — not management PAT |
| `JWT_SECRET_CLOUD` | **Empty** | Required before Render |
| `ALLOWED_ORIGINS_CLOUD` | **Empty** | Required before Render |
| `API_PUBLIC_URL_CLOUD` | **Empty** | Required before Render |
| Local `OWNER_DATABASE_URL` / `APP_DATABASE_URL` | **Unchanged** (`localhost`) | Local PG19 |

**Credential classification**

- `SUPABASE_ACCESS_TOKEN` → Supabase Management API personal access token.  
- `S3_ACCESS_KEY` / `S3_SECRET_KEY` → Storage S3 credentials (not a management token).

**Fix applied during audit:** removed duplicate blank `API_PUBLIC_URL=` that would have wiped the local API URL (last-key-wins). Cloud placeholder is `API_PUBLIC_URL_CLOUD`.

## 3. Connectivity

| Mode | Result |
|------|--------|
| Direct `db.<ref>.supabase.co` | **Unavailable** from this network (DNS failure) |
| Session pooler `:5432` | **PASS** (used for owner + app) |
| Transaction pooler `:6543` | Not required for this phase |

## 4. Database / migrations

| Check | Result |
|-------|--------|
| Pre-migrate public tables | **0** (clean) |
| Alembic upgrade head | **PASS** → `0027_saas_payment_reliability` |
| Public tables after | **75** |
| RLS-enabled tables | **57** (FORCE on) |
| `hos_app` BYPASSRLS | **false** |
| `hos_app` DDL | Denied |
| Two-tenant RLS drill | **PASS** (see role review) |

## 5. Storage

| Item | Result |
|------|--------|
| Adapter | Application `S3StorageAdapter` (`STORAGE_ADAPTER=s3`) |
| Bucket | `dental-os` (existing; not deleted/recreated) |
| Suggested `healthcare-documents-staging` | Not created — reused existing private bucket |
| Provider isolation drill | Completed against real endpoint (see security doc) |

## 6. Remaining manual actions

1. Fill `JWT_SECRET_CLOUD`, `ALLOWED_ORIGINS_CLOUD`, `API_PUBLIC_URL_CLOUD` before Render.  
2. Decide whether to grant `BYPASSRLS` to **`hos_owner` only** (parity with local) — **approval required**.  
3. Prefer distinct passwords for postgres / `hos_owner` / `hos_app` (currently shared staging secret).  
4. Optionally create dedicated bucket `healthcare-documents-staging` and update `S3_BUCKET`.  
5. Rotate staging secrets if this environment file was exposed outside the machine.  
6. Do not enable public Storage policies on clinical buckets.

## 7. Next phase

**P3.7B — Render API deployment** using `docs/deployment/P3-7A-render-environment-mapping.md`.
