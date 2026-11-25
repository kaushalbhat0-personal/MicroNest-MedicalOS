# P3.7B — Backend Staging Smoke Test Report

**Date:** 2026-11-24  
**Verdict:** **CONDITIONAL PASS** — staging API live for synthetic testing; authenticated tenant flows not exercised (empty seed).

## 1. Render service identity and branch

| Field | Value |
|-------|-------|
| Name | `MicroNest-MedicalOS` |
| Service ID | `srv-dc2tmb49v7es73dkqc9g` |
| URL | `https://micronest-medicalos.onrender.com` |
| Branch | `release/p3-7b-staging` |
| Runtime | Native Python (`python`) |
| Health check | `/api/healthz` |
| Build | Filtered `pip install` from `backend/requirements.txt` (excludes `pgserver` / pytest / ruff / mypy — local-only) |
| Start | `python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT` |
| `PYTHON_VERSION` | `3.10.14` |

## 2. Auto-deploy

**Disabled** (`autoDeploy=no`). Remains disabled after this controlled deploy.

## 3. Environment configuration (names / status only)

| Name | Status |
|------|--------|
| `ENV` | set (`preview`) |
| `DEPLOYMENT` | set (`cloud`) |
| `COOKIE_SECURE` | set (`true`) |
| `DB_SSL_REQUIRE` | set (`true`) |
| `APP_DATABASE_URL` | set — `hos_app.<ref>` session pooler, db `healthcare_os_preview`, `sslmode=require` |
| `JWT_SECRET` | set — length 64; differs from local `JWT_SECRET`; staging-only |
| `API_PUBLIC_URL` | set — Render HTTPS URL |
| `ALLOWED_ORIGINS` | set — `["https://micronest-medicalos.onrender.com"]` (API self-origin until Vercel) |
| `STORAGE_ADAPTER` | set (`s3`) |
| `S3_ENDPOINT_URL` / `S3_BUCKET` / `S3_REGION` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` / `S3_USE_TLS` / `S3_ENSURE_BUCKET` | set |
| `NOTIFY_PROVIDER` / `DEV_NOTIFICATIONS_ALLOW` / `SAAS_PAYMENT_PROVIDER` | set |
| `PYTHON_VERSION` | set |
| `OWNER_DATABASE_URL` | **not** on runtime (correct) |
| `RENDER_API_KEY` | **not** on runtime (correct) |

CORS: not wildcard. Frontend origin unresolved — kept API URL only; extend when Vercel ships.

## 4. Database connectivity, role, Alembic

| Check | Result |
|-------|--------|
| `hos_app` via session pooler + SSL | **PASS** (`/api/readyz` ready; direct probe `current_user=hos_app`) |
| `rolbypassrls` | **false** |
| Alembic revision | **`0027_saas_payment_reliability`** (read via `hos_owner` ops URL) |
| `hos_app` SELECT `alembic_version` | **DENIED** (expected least privilege) |
| `hos_app` CREATE TABLE / ALTER TABLE | **DENIED** |
| RLS without tenant context (`locations` count) | **0 rows** |

Migrations were **not** run through the runtime role.

## 5. Storage adapter and synthetic isolation

Adapter: `S3StorageAdapter` → Supabase S3-compatible endpoint, bucket `dental-os`, region `eu-west-3`.

| Case | Result |
|------|--------|
| Private upload + authorized get (tenant A) | **PASS** |
| Distinct A/B payloads | **PASS** |
| Public object URL denied | **PASS** |
| Presigned GET fetch | **PASS** |
| Expired signed URL denied | **PASS** |
| Tampered signed URL denied | **PASS** |
| Path traversal key rejected | **PASS** |
| Per-tenant IAM / bucket policy | **NOT PROVEN** — shared account/bucket credential |

Synthetic keys cleaned up after drill. Signed URL query strings not logged.

## 6. Health endpoints

| Endpoint | Result |
|----------|--------|
| `GET /api/healthz` | **200** `{"status":"ok"}` (process liveness only) |
| `GET /api/readyz` | **200** `{"status":"ready"}` (DB reachable as app role) |

## 7. Authentication and tenant isolation

| Case | Result |
|------|--------|
| Unauthenticated `GET /api/v1/auth/me` | **401** |
| Unauthenticated patients list | **401** |
| Bad login credentials | **401** |
| `X-Tenant-Id` alone (no auth) | **401** — tenant not inferred from client header |
| Authenticated synthetic tenant context | **SKIP** — staging DB has `users=0`, `tenants=0`; no smoke account configured |
| Cross-tenant API denial with auth | **SKIP** (depends on synthetic accounts) |

## 8. Deployment

| Field | Value |
|-------|-------|
| Deploy ID | `dep-dc2ua03m8hqs73aca9d0` |
| Commit SHA | `293dc668e7117f20a4b88e7a3047aa8e501c99b6` |
| Terminal status | **live** |
| Prior failures | `dep-dc2u8du1egvs73frq6o0` (missing root Dockerfile / docker runtime); `dep-dc2u8vjl550s73c88eq0` (`pgserver` pip fail on Python 3.14) — remediated via native Python 3.10 + filtered requirements |

## 9. Exact tests run

Executed via `scripts/_p37b_staging_smoke.py` and `scripts/_p37b_final_verify.py` against live HTTPS + cloud DB/S3 (results also in `scripts/_p37b_smoke_results.json`). All executed checks **PASS**; auth-tenant with sessions **SKIP**.

## 10. Blockers, risks, unresolved decisions

1. **No synthetic seed users/tenants** — authenticated API/tenant/cross-tenant HTTP tests remain open until a staging seed or smoke credentials exist.
2. **Vercel frontend origin unknown** — `ALLOWED_ORIGINS` temporarily lists the API URL only; must be updated when frontend deploys (no wildcard).
3. **Shared S3 credential** — isolation is application-layer (server keys + auth), not per-tenant IAM.
4. **Build command filters local-only deps** — prefer a committed `requirements-prod.txt` later to avoid `sed` in build.
5. **JWT on Render** is a strong staging secret distinct from local `JWT_SECRET`; keep `JWT_SECRET_CLOUD` docs/process aligned for operators.

## 11. Safe for synthetic-data testing?

**Yes**, for API liveness, DB readiness, unauthenticated denial, and provider storage drills with synthetic bytes only.

## 12. Real patient data blocked?

**Yes.** Staging DB has zero users/tenants; no patient seed; smoke used only synthetic storage payloads and invalid login emails. Production/`main` untouched. Real PHI remains out of scope.
