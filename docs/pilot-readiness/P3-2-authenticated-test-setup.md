# P3.2 — Authenticated test setup

**HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3` (unchanged; no commit)  
**Local DB:** PostgreSQL 19 · `healthcare_os` (API) · `healthcare_os_test` (pytest, serial only)

## Why authenticated tests were previously skipped

| Cause | Detail |
|-------|--------|
| API down | No local `healthcare_os` database; uvicorn not running |
| Credentials | `PLAYWRIGHT_OWNER_EMAIL` / `PLAYWRIGHT_OWNER_PASSWORD` unset |
| Cookie hostname | `localhost:3000` → `127.0.0.1:8000` is cross-site; `SameSite=Lax` cookies were not sent on `fetch` |
| Rate limits | Default `LOGIN_IP_LIMIT_PER_MIN=10` exhausted mid-suite |

This is an environment gap, not an application defect.

## Prerequisites

1. PostgreSQL 19 running locally (service `postgresql-x64-19`).
2. Databases: `healthcare_os` (app) and `healthcare_os_test` (pytest).
3. Roles `hos_owner` / `hos_app` with passwords from root `.env`.
4. Python venv at `.venv`, Node workspaces installed.
5. Chromium for Playwright (`npm run test:e2e:install -w @healthcare-os/web`).

## Environment variables (root `.env`, gitignored)

| Variable | Purpose |
|----------|---------|
| `OWNER_DATABASE_URL` / `APP_DATABASE_URL` | App boot against `healthcare_os` |
| `TEST_*_DATABASE_URL` | Pytest against `healthcare_os_test` only |
| `JWT_SECRET`, `ENV=dev`, `DEV_NOTIFICATIONS_ALLOW=true` | Dev auth + notification surrogate |
| `ALLOWED_ORIGINS` | Must include the **exact** web origin (`http://localhost:3000`) |
| `NEXT_PUBLIC_API_URL` | Must be `http://localhost:8000` when web is on `localhost:3000` |
| `PLAYWRIGHT_OWNER_EMAIL` / `PLAYWRIGHT_OWNER_PASSWORD` | Seeded owner smoke |
| `PLAYWRIGHT_BASE_URL` | `http://localhost:3000` |
| `LOGIN_IP_LIMIT_PER_MIN` / `LOGIN_ACCOUNT_LIMIT_PER_MIN` | Raise for local e2e (e.g. 120 / 60) |

`apps/web/.env.local` (gitignored via `.env.*`) mirrors `NEXT_PUBLIC_API_URL=http://localhost:8000`.

## Deterministic procedure

```powershell
# 1. Create DB if missing (non-destructive)
$env:PGPASSWORD='owner-dev-pass'
& "C:\Program Files\PostgreSQL\19\bin\psql.exe" -U hos_owner -h 127.0.0.1 -d postgres `
  -c "CREATE DATABASE healthcare_os OWNER hos_owner;"   # ignore if exists

# 2. Migrate + app role (OWNER_DATABASE_URL from .env)
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
Push-Location backend; ..\.venv\Scripts\python.exe -m app.platform.ops ensure-app-role; Pop-Location

# 3. Synthetic owner (no tenant — UI creates workspace)
.\.venv\Scripts\python.exe .\scripts\p32_seed_owner.py

# 4. API (same hostname family as the web app)
$env:LOGIN_IP_LIMIT_PER_MIN='120'
$env:LOGIN_ACCOUNT_LIMIT_PER_MIN='60'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000

# 5. Web
$env:NEXT_PUBLIC_API_URL='http://localhost:8000'
npm run web:dev

# 6. Authenticated Playwright
$env:PLAYWRIGHT_BASE_URL='http://localhost:3000'
$env:NEXT_PUBLIC_API_URL='http://localhost:8000'
npm run test:e2e -w @healthcare-os/web
```

### Portal password helper (test-only)

After staff enrolls a portal user, Playwright may call:

```powershell
.\.venv\Scripts\python.exe .\scripts\p32_set_user_password.py --email <email> --password <pw>
```

Refuses `ENV` in `preview` / `prod` / `production`. Never prints the password.

## Cleanup policy

- Do **not** drop or reset `healthcare_os` / `healthcare_os_test`.
- Synthetic users/tenants use unique emails/slugs (`p32.*@example.com`); leave them or delete by email if needed.
- No Docker. No payment changes. No destructive shared-DB resets.

## BLOCKED vs skip

Authenticated journeys call `requireApi` / `requireOwnerCreds` and **fail with `BLOCKED:`** when API or owner env is missing. Silent skip is not used for auth prerequisites.

Heavy invite/portal/isolation specs run once on `desktop-1280` (other projects skip with an explicit reason) to avoid rate-limit and duplicate fixture noise — not counted as pass.
