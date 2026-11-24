# P3.7A — Render Environment Mapping (prepared, not deployed)

**Date:** 2026-11-24  
**Status:** Mapping only — **no Render service created in this phase**

## Placeholder → runtime name

| Local / planning key | Render / runtime key | Notes |
|----------------------|----------------------|-------|
| `OWNER_DATABASE_URL_CLOUD` | `OWNER_DATABASE_URL` | Session pooler `hos_owner.<ref>`; migrations job only |
| `APP_DATABASE_URL_CLOUD` | `APP_DATABASE_URL` | Session pooler `hos_app.<ref>`; API + worker |
| `APP_ROLE_PASSWORD_CLOUD` | `APP_ROLE_PASSWORD` | If using `ensure_app_role` ops |
| `STORAGE_ADAPTER_CLOUD` | `STORAGE_ADAPTER` | Must be `s3` |
| `S3_ENDPOINT_URL` | `S3_ENDPOINT_URL` | Same name |
| `S3_BUCKET` | `S3_BUCKET` | |
| `S3_REGION` | `S3_REGION` | |
| `S3_ACCESS_KEY` | `S3_ACCESS_KEY` | App name (not `S3_ACCESS_KEY_ID`) |
| `S3_SECRET_KEY` | `S3_SECRET_KEY` | App name (not `S3_SECRET_ACCESS_KEY`) |
| `S3_USE_TLS` | `S3_USE_TLS` | `true` |
| `S3_ENSURE_BUCKET` | `S3_ENSURE_BUCKET` | Keep `false` in staging/prod |
| `JWT_SECRET_CLOUD` | `JWT_SECRET` | **Still empty — generate ≥32 bytes** |
| `ALLOWED_ORIGINS_CLOUD` | `ALLOWED_ORIGINS` | JSON list of exact Vercel origins |
| `API_PUBLIC_URL_CLOUD` | (ops/docs) | Public Render URL; also bake into Vercel `NEXT_PUBLIC_API_URL` |

## Required topology flags (Render)

```
ENV=preview          # or prod when ready
DEPLOYMENT=cloud
COOKIE_SECURE=true
DB_SSL_REQUIRE=true
DEV_NOTIFICATIONS_ALLOW=false
NOTIFY_PROVIDER=none
```

## Do not set on Vercel

- Any `*_DATABASE_URL*`
- `APP_ROLE_PASSWORD*`
- `JWT_SECRET*`
- `S3_ACCESS_KEY` / `S3_SECRET_KEY`
- `SUPABASE_ACCESS_TOKEN`

Vercel only needs public web config, primarily:

```
NEXT_PUBLIC_API_URL=<Render API https URL>
```

## Still empty (block Render boot validation)

| Variable | Status |
|----------|--------|
| `JWT_SECRET_CLOUD` | EMPTY |
| `ALLOWED_ORIGINS_CLOUD` | EMPTY |
| `API_PUBLIC_URL_CLOUD` | EMPTY |
| `RENDER_API_SERVICE_NAME` | EMPTY |
| `VERCEL_PROJECT_NAME` / `NEXT_PUBLIC_API_URL_CLOUD` | EMPTY |

## Local safety

Local `.env` keeps:

- `OWNER_DATABASE_URL` / `APP_DATABASE_URL` → localhost  
- `STORAGE_ADAPTER` unset/local via `STORAGE_LOCAL_ROOT`  
- Cloud values only under `*_CLOUD` / shared `S3_*` keys used by staging drills

When running the API locally, do **not** export cloud `OWNER_DATABASE_URL` unless intentionally targeting staging.
