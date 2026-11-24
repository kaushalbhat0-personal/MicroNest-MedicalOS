# P3.7B — Secret Handling Review

**Date:** 2026-11-24

## Controls followed

| Control | Status |
|---------|--------|
| `.env` gitignored and not staged/committed | **Pass** |
| `RENDER_API_KEY` never printed / never written to repo | **Pass** |
| `RENDER_API_KEY` not added to Render service env | **Pass** (also cannot write env via API) |
| Supabase PAT / S3 secrets / DB URLs not in commit | **Pass** (staged secret scan) |
| Staging `JWT_SECRET_CLOUD` generated locally, not echoed | **Pass** |
| Docs contain names/shapes only, not values | **Pass** |

## Staged scan note

`tests/conftest.py` contains **local test** default URLs (`owner-dev-pass` / `change-me-app-role` on `127.0.0.1`). These are harness defaults, not cloud staging secrets.

## Residual risks

1. Render API key currently has **read-only** service scope — operators must use the dashboard or a broader key for env updates.  
2. When env vars are applied via `PUT /env-vars`, Render **replaces** the full set — preserve existing keys by reading first (requires env-var read scope).  
3. Rotate any credential that may have appeared in local agent/chat context earlier in P3.7A.
