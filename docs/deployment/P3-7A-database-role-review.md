# P3.7A — Database Role Review (Supabase Staging)

**Date:** 2026-11-24  
**Project:** `MicroNest-MedicalOS` (`dimhmkfiqdlpxiafqnxl`)

## Local baseline

| Role | Purpose | Notes |
|------|---------|-------|
| `hos_owner` | Migrations / seeds / ops | Local: `BYPASSRLS=true` (observed) |
| `hos_app` | Runtime API | Least privilege; RLS policies `TO hos_app`; no BYPASSRLS |

Migrations create `hos_app` as `NOLOGIN` then ops/`ensure_app_role` enables login. Grants are per-table in Alembic.

## Cloud roles created

| Role | Login | Super | BYPASSRLS | Notes |
|------|-------|-------|-----------|-------|
| `hos_owner` | yes | no | **no** | Created on staging; DDL on `public` verified |
| `hos_app` | yes | no | **no** | DDL denied; RLS effective |
| `postgres` (platform) | yes | no* | **yes** | Supabase platform role (`*` not `rolsuper`, but elevated) |

\* On Supabase, `postgres` reports `rolsuper=false` but `rolbypassrls=true` and `createrole=true`.

## Connection usernames (session pooler)

Supabase pooler requires `role.project_ref`:

- Owner: `hos_owner.dimhmkfiqdlpxiafqnxl@…pooler…:5432`
- App: `hos_app.dimhmkfiqdlpxiafqnxl@…pooler…:5432`

## Privilege verification

| Test | Result |
|------|--------|
| `hos_owner` CREATE/DROP TABLE | PASS |
| `hos_app` CREATE TABLE | Denied (PASS) |
| `hos_app` `rolbypassrls` | false (PASS) |
| `hos_app` SELECT `locations` without `app.tenant_id` | 0 rows (PASS) |
| Cross-tenant UPDATE as `hos_app` | 0 rowcount (PASS) |
| Tenant A sees only A location | PASS |
| Tenant B sees only B location | PASS |

## Documented difference vs local (approval needed)

Local `hos_owner` has **`BYPASSRLS=true`**, so owner-session DML works under `FORCE ROW LEVEL SECURITY`.  
Cloud `hos_owner` has **`BYPASSRLS=false`**, so owner DML into RLS tables is denied (no policy `TO hos_owner`).

**Impact:** Staging seed/ops inserts that rely on owner bypass must use the platform `postgres` role, or we grant `BYPASSRLS` to `hos_owner` only.

**Recommendation (not applied — elevated privilege):**  
`ALTER ROLE hos_owner BYPASSRLS;` — restores local ops parity. **Do not** grant BYPASSRLS to `hos_app`.

## What was not done

- No password rotation of the Supabase `postgres` user.  
- No weakening of RLS policies.  
- No `BYPASSRLS` granted without approval.
