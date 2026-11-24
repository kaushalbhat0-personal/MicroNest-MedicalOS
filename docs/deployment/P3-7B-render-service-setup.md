# P3.7B — Render Service Setup (`healthcare-os-api-staging`)

**Date:** 2026-11-24  
**Status:** **NOT CREATED** — no Render API key / CLI credentials in environment  
**Action required:** Create the service in the Render dashboard using this checklist.

## Account / access

| Check | Result |
|-------|--------|
| `RENDER_API_KEY` / token in `.env` | Missing |
| Render CLI / `~/.render` | Missing |
| Automated service create | **Blocked** |

## Service settings (dashboard)

| Field | Value |
|-------|-------|
| Name | `healthcare-os-api-staging` |
| Type | Web Service |
| Region | Prefer **Frankfurt (EU)** (align with Supabase `eu-west-3`) |
| Runtime | **Python 3** |
| Repo | `https://github.com/kaushalbhat0-personal/MicroNest-MedicalOS.git` |
| Branch | **Requires approval** — committed `main` is `2a0974e…` and **does not** include uncommitted backend work needed for current app |
| Root Directory | *(empty / repo root)* |
| Build Command | `pip install -r backend/requirements.txt` |
| Start Command | `python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/healthz` |
| Auto-Deploy | Disable until a release branch is approved and pushed |

## Expected URL

`https://healthcare-os-api-staging.onrender.com`  
(Set `API_PUBLIC_URL` / `API_PUBLIC_URL_CLOUD` to this after create.)

## Release candidate note

Do **not** deploy raw `main@2a0974e` expecting P3.6/P3.7 behavior.  
Working tree contains required changes (dental storage keys, consent gate, migrations 0018–0027, etc.) that are **uncommitted**.

**Stop:** Pushing a deployment branch requires explicit approval.

## One-off migration job (optional)

Staging preview DB is already at `0027_saas_payment_reliability`.  
Do **not** re-run migrations on boot. If a one-off is needed later:

- Separate Render **One-Off Job** / shell with `OWNER_DATABASE_URL` only  
- Command: `alembic -c backend/alembic.ini upgrade head`  
- Never put `OWNER_DATABASE_URL` on the long-running web service if avoidable
