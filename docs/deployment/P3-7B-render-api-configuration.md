# P3.7B — Render API Configuration

**Date:** 2026-11-24  
**Deployment triggered:** **No**

## Service identity (discovered)

| Field | Value |
|-------|-------|
| Service ID | `srv-dc2tmb49v7es73dkqc9g` |
| Name | `MicroNest-MedicalOS` |
| Type | `web_service` |
| Repo | `https://github.com/kaushalbhat0-personal/MicroNest-MedicalOS` |
| URL | `https://micronest-medicalos.onrender.com` |
| Branch (current) | **`main`** (unchanged — API write denied) |
| Auto-deploy (current) | **`yes`** (unchanged — API write denied) |

Sole matching service for this workspace/key → unambiguous.

## API key capability

`RENDER_API_KEY` is present locally and can **list/read** the service.

Write attempts returned **403 insufficient_token_scope**:

| Operation | Result |
|-----------|--------|
| `PATCH /services/{id}` (branch / autoDeploy) | **403** needs `services.read_write` |
| `GET/PUT /services/{id}/env-vars` | **403** needs env-var Read & write |

**Blocker:** Expand the API key scopes in Render Dashboard → Account/Workspace API Keys:

1. Services: **Read & write**
2. Environment variables and secret files: **Read & write**

Then re-run configuration (or apply the dashboard steps below). Do **not** put `RENDER_API_KEY` into service env vars.

## Required runtime variables (application names)

Set these on the service (values from local `*_CLOUD` / S3 keys — never commit):

| Render env name | Source |
|-----------------|--------|
| `ENV` | `preview` |
| `DEPLOYMENT` | `cloud` |
| `COOKIE_SECURE` | `true` |
| `DB_SSL_REQUIRE` | `true` |
| `DEV_NOTIFICATIONS_ALLOW` | `false` |
| `NOTIFY_PROVIDER` | `none` |
| `SAAS_PAYMENT_PROVIDER` | `mock` |
| `APP_DATABASE_URL` | `APP_DATABASE_URL_CLOUD` (`hos_app` session pooler, `healthcare_os_preview`, `sslmode=require`) |
| `JWT_SECRET` | `JWT_SECRET_CLOUD` (generated staging secret) |
| `API_PUBLIC_URL` | `https://micronest-medicalos.onrender.com` |
| `ALLOWED_ORIGINS` | `["https://micronest-medicalos.onrender.com"]` until Vercel exists |
| `STORAGE_ADAPTER` | `s3` |
| `S3_ENDPOINT_URL` | local `S3_ENDPOINT_URL` |
| `S3_BUCKET` | local `S3_BUCKET` |
| `S3_REGION` | local `S3_REGION` |
| `S3_ACCESS_KEY` | local `S3_ACCESS_KEY` (**not** `S3_ACCESS_KEY_ID`) |
| `S3_SECRET_KEY` | local `S3_SECRET_KEY` |
| `S3_USE_TLS` | `true` |
| `S3_ENSURE_BUCKET` | `false` |

**Do not** set on the web service (unless a separate one-off job):

- `OWNER_DATABASE_URL`
- `RENDER_API_KEY`
- `SUPABASE_ACCESS_TOKEN`
- Any `NEXT_PUBLIC_*` secrets

## Dashboard steps (until API scopes granted)

1. Open service `MicroNest-MedicalOS`.
2. Settings → disable **Auto-Deploy**.
3. Settings → Branch → `release/p3-7b-staging` (do not deploy yet).
4. Environment → add/update the table above (merge; do not wipe unrelated vars if any exist — with API we could not read existing keys due to 403).
5. **Do not** click Manual Deploy until the next approved phase.

## Build / start (confirm on service)

| Setting | Value |
|---------|-------|
| Runtime | Python 3 |
| Build | `pip install -r backend/requirements.txt` |
| Start | `python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT` |
| Health | `/api/healthz` |
