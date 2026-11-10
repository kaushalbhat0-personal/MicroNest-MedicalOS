# Portal browser E2E harness (scratch-environment only)

Authenticated Playwright coverage for the patient portal that cannot run
against the pytest suite (which has no browser) and must not run against
shared databases.

## What it proves

- Portal-only login routes to `/portal` (not provider `/`); staff login keeps `/`.
- Portal header carries tenant + patient identity and a working sign-out.
- All 8 portal sections render seeded data with no horizontal overflow
  (320 / 390 / 430 / 768 / 1024 / 1280 / 1536).
- Appointment detail: cancel dialog traps focus, Escape closes it, focus
  returns to the trigger, confirm flips status to Cancelled.
- Reduced-motion emulation yields zero-duration transitions.
- No page errors; only expected 401 console entries for logged-out fetches.

## Requirements (NOT repo dependencies)

- Node + `playwright-core` (`npm i playwright-core` in any scratch dir)
- A Chromium build visible to playwright-core
  (`$env:PLAYWRIGHT_BROWSERS_PATH` or the default cache location)
- A scratch Postgres database, migrated to head, seeded with
  `seed_portal.py` (creates `maya@example.com / Portal-pass-12345` plus a
  full clinical/billing fixture; destructive cancel test consumes the seeded
  appointment, so re-seed before re-running)

## Run

```powershell
# 1. scratch backend on :8001 (example env; keep secrets out of the repo)
$env:APP_DATABASE_URL='postgresql+psycopg2://hos_app:<pw>@127.0.0.1:5432/<scratchdb>'
$env:JWT_SECRET='<min-32-char-secret>'
$env:ALLOWED_ORIGINS='["http://localhost:3002"]'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001

# 2. frontend dev server against the scratch API
$env:NEXT_PUBLIC_API_URL='http://localhost:8001'
npx next dev -p 3002   # from apps/web

# 3a. full matrix: 7 viewports, 8 sections with seeded data, cancel command,
#     reduced-motion, console/page-error sweep
node scripts/portal-e2e/portal_e2e.js

# 3b. routing + focus + hydration: portal-only login routes to /portal,
#     staff login keeps /, sign-out lands on /login, Escape returns focus
#     to the trigger, zero hydration mismatches
$env:NODE_PATH='<path-to>\node_modules'   # needs playwright-core installed
node scripts/portal-e2e/portal_routing_focus.js
```

Exit 0 with a JSON report on stdout; `errors: []` means no page or
unexpected console errors. `FATAL` on harness failure (not a product verdict).

## Notes

- The harness mutates the scratch appointment (cancel flow). Re-seed for
  repeat runs; never point it at a shared database.
- `seed_portal.py` uses `sys.path` to import the repo backend; run it from
  the repo root.
