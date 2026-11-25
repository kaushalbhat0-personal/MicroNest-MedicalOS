# P3.7B — Next Deployment Step

**Backend staging deploy:** complete (`dep-dc2ua03m8hqs73aca9d0` **live**).  
See `P3-7B-backend-smoke-test.md` for evidence.

## Completed

1. Branch `release/p3-7b-staging` committed + pushed.  
2. Render service `MicroNest-MedicalOS` (`srv-dc2tmb49v7es73dkqc9g`) on branch `release/p3-7b-staging`, **auto-deploy off**.  
3. Runtime env configured (hos_app pooler, staging JWT, S3, restricted CORS).  
4. Native Python 3.10 runtime; filtered build (excludes local-only `pgserver`/test tools).  
5. Smoke: healthz/readyz, DB role/DDL/Alembic 0027, unauth denial, synthetic S3 isolation.

## Remaining

1. Seed synthetic staging tenants/users (or set `STAGING_SMOKE_EMAIL` / `STAGING_SMOKE_PASSWORD`) and re-run authenticated + cross-tenant API checks.  
2. Deploy Vercel frontend; then extend `ALLOWED_ORIGINS` to the real frontend origin (never `*`).  
3. Optional: commit `backend/requirements-prod.txt` and point Render build at it (replace `sed` filter).  
4. Align operator docs so `JWT_SECRET_CLOUD` matches the Render staging secret process.

## Explicit non-goals

- No production deploy  
- No `main` push  
- No auto-deploy  
- No BYPASSRLS on `hos_app`  
- No real patient data  
- No SaaS payment live keys
