# P1.5 Operations E2E — status and manual verification

## Automated Playwright (staff Operations)

**Blocker:** There is no staff/clinic Operations Playwright suite in this repository.

Existing browser harnesses:

| Path | Scope |
|------|--------|
| `scripts/portal-e2e/` | Patient portal only (Playwright via `playwright-core`, scratch DB) |
| `apps/web` | Vitest unit/component tests — no Playwright config |

`package.json` / `apps/web` do not declare a Playwright project for staff journeys. Portal E2E requires a scratch Postgres DB, separate uvicorn + Next ports, and `playwright-core` installed outside the monorepo deps (see `scripts/portal-e2e/README.md`).

Therefore staff Operations E2E was **not executed** in P1.5.

## Covered by automated non-browser tests

- Dashboard composition, isolation, role section omission — `tests/api/test_operations_dashboard.py`
- Appointment metric COUNTs + truncated detail meta — same module
- Follow-up location service-day midnight + snoozed/completed exclusion — same module
- Outstanding SQL aggregate vs `outstanding_for_invoice` — `tests/service/test_outstanding_aggregate_reconcile.py`
- Operations UI loading / metrics / truncated banner / forbidden — `apps/web/app/operations/page.test.tsx`

## Manual verification (reproducible)

Prerequisites: local API + `apps/web` against `healthcare_os_test` (or another migrated scratch DB); synthetic staff user with clinic membership.

1. Sign in as synthetic clinic staff (tenant_admin or doctor with ops permissions).
2. Select an authorized clinic/tenant if multi-membership.
3. Open **Operations** (`/operations`). Confirm location service-day line and metrics load.
4. Confirm today’s appointments table; if volume &gt; 50, confirm **Partial list** banner.
5. Navigate to **Reception**; confirm board loads for the same location.
6. Return to **Operations** (browser back or nav).
7. Open **Follow-ups**; note UTC bucket copy vs Operations “location service day” KPIs.
8. Sign in as a restricted role (e.g. nurse without `billing.read`). Confirm Billing section omitted / nav lacks unauthorized items; APIs still return 403 for forbidden domains.

Portal-only users must continue to land on `/portal` (existing portal routing coverage).
