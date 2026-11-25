# P3.7B — Render API Configuration

**Date:** 2026-11-24  
**Deployment triggered:** **Yes** — `dep-dc2ua03m8hqs73aca9d0` → **live**

## Service identity

| Field | Value |
|-------|-------|
| Service ID | `srv-dc2tmb49v7es73dkqc9g` |
| Name | `MicroNest-MedicalOS` |
| Type | `web_service` |
| Repo | `https://github.com/kaushalbhat0-personal/MicroNest-MedicalOS` |
| URL | `https://micronest-medicalos.onrender.com` |
| Branch | **`release/p3-7b-staging`** |
| Auto-deploy | **`no`** |
| Runtime | Native Python 3.10.14 |

## API key capability

Workspace API key scopes include Services + Environment variables **Read & write** (earlier 403s cleared).  
`RENDER_API_KEY` is **not** set as a service runtime variable.

## Runtime variables (application names)

| Render env name | Notes |
|-----------------|-------|
| `ENV` | `preview` |
| `DEPLOYMENT` | `cloud` |
| `COOKIE_SECURE` | `true` |
| `DB_SSL_REQUIRE` | `true` |
| `DEV_NOTIFICATIONS_ALLOW` | `false` |
| `NOTIFY_PROVIDER` | `none` |
| `SAAS_PAYMENT_PROVIDER` | `mock` |
| `APP_DATABASE_URL` | `hos_app` session pooler, `healthcare_os_preview`, `sslmode=require` |
| `JWT_SECRET` | staging-only secret (64 chars); not local `JWT_SECRET` |
| `API_PUBLIC_URL` | `https://micronest-medicalos.onrender.com` |
| `ALLOWED_ORIGINS` | `["https://micronest-medicalos.onrender.com"]` until Vercel exists |
| `STORAGE_ADAPTER` | `s3` |
| `S3_ENDPOINT_URL` / `S3_BUCKET` / `S3_REGION` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` | set |
| `S3_USE_TLS` | `true` |
| `S3_ENSURE_BUCKET` | `false` |
| `PYTHON_VERSION` | `3.10.14` |

**Not** on the web service:

- `OWNER_DATABASE_URL`
- `RENDER_API_KEY`
- `SUPABASE_ACCESS_TOKEN`

## Build / start / health

| Setting | Value |
|---------|-------|
| Runtime | Python |
| Build | `sed '/^pgserver/d;/^pytest/d;/^ruff/d;/^mypy/d' backend/requirements.txt > /tmp/requirements-runtime.txt && pip install -r /tmp/requirements-runtime.txt` |
| Start | `python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT` |
| Health | `/api/healthz` |

**Why filtered build:** full `requirements.txt` includes `pgserver` (no Linux cloud wheel) and fails pip. Prefer a future committed `requirements-prod.txt`.

**Prior failure modes:** Docker runtime pointed at missing root `./Dockerfile`; Python 3.14 default + `pgserver`. Remediated without changing application source.

## CORS decision

Frontend not deployed. Application requires non-empty `ALLOWED_ORIGINS` at boot. Staging uses the API HTTPS origin only — restricted, not `*`. Update when Vercel origin is known.
