# P3.2 — Implementation report

**Verdict:** **CONDITIONAL PASS** (synthetic authenticated pilot rehearsal)  
**HEAD before/after:** `2a0974e41af9e334e147794f45e258f34d6814d3` (no commit / push / stash / reset)  
**Payments / migrations:** untouched (Alembic already at `0027_saas_payment_reliability` on local `healthcare_os`)

## Why not full PASS

Acceptance requires no critical pilot security issue unresolved. P3.0 Risks that remain open for **real PHI / production storage**:

1. Client-supplied document `storage_key` (shared bucket without server-bound prefix).  
2. Dental consent not hard-gated before procedure.

For **synthetic local storage**, those are documented Risks, not blockers — matching P3.0. Full PASS is withheld so the verdict is not inflated.

## What closed the P3.1-C gap

| Gap | Resolution |
|-----|------------|
| API unavailable | Created `healthcare_os`, migrated to head, started uvicorn |
| No owner credentials | `scripts/p32_seed_owner.py` + env vars |
| Silent skip | `requireApi` / `requireOwnerCreds` → **BLOCKED** failure |
| Cookie/CORS hostname | Web + API on `localhost`; `ALLOWED_ORIGINS` includes both hosts |
| Auth journeys unverified | Playwright owner / invite / portal / isolation green |

## Files added/changed (P3.2)

| Path | Role |
|------|------|
| `scripts/p32_seed_owner.py` | Synthetic owner seed (dev-only) |
| `scripts/p32_set_user_password.py` | Portal activate helper (dev-only) |
| `apps/web/e2e/helpers.ts` | Health, BLOCKED, login waits |
| `apps/web/e2e/authenticated-journeys.spec.ts` | Owner, invite, portal, isolation |
| `apps/web/e2e/onboarding-journeys.spec.ts` | Public + seeded smoke |
| `apps/web/playwright.config.ts` | 1440 / 1280 / 390; load root `.env` |
| `apps/web/next.config.mjs` | `allowedDevOrigins` |
| `apps/web/lib/api.ts` | Default API host `localhost` |
| `docs/pilot-readiness/P3-2-*.md` | Setup, journeys, security |
| `docs/ui-ux/P3-2-*.md` | Visual QA + this report |
| `docs/ui-ux/screenshots/p32-*.png` | Visual evidence |

## Test gates (exact)

| Gate | Command | Result |
|------|---------|--------|
| Isolation | `pytest tests/isolation -q` | **38 passed** |
| Portal-focused | `pytest tests -k portal -q` | **33 passed** |
| Web TypeScript | `npm run web:typecheck` | Pass |
| Web Vitest | `npm run test -w @healthcare-os/web` | **44 passed** (5 files) |
| UI TypeScript | `npm run ui:typecheck` | Pass |
| UI tests | `npm run ui:test` | **17 passed** |
| Next production build | `npm run web:build` | Pass |
| Playwright | `npm run test:e2e -w @healthcare-os/web` | **14 passed · 4 skipped** (intentional single-project heavy journeys) |

Database tests run serially. Skipped Playwright cases are project-scoped duplicates, not missing-prereq skips.

## Remaining blockers

| Item | Blocks |
|------|--------|
| Document `storage_key` server binding | Real-patient / shared object storage |
| Dental consent hard-gate | Real clinical procedure pilot claims |
| Production email delivery | Ops dependency only; not claimed green |
| Login rate limits at defaults | Local e2e needs raised limits or spaced runs |

## Approvals

| Question | Answer |
|----------|--------|
| Synthetic-data pilot rehearsal approved? | **Yes** (local API + web + synthetic fixtures) |
| Real-patient-data use approved? | **No — remains blocked** |
