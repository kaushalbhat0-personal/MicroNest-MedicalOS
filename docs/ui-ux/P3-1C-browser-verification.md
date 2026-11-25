# P3.1-C — Browser verification

## Playwright setup

| Item | Value |
|------|-------|
| Package | `@playwright/test@1.51.1` (web workspace) |
| Config | `apps/web/playwright.config.ts` |
| Specs | `apps/web/e2e/onboarding-journeys.spec.ts` |
| Scripts | `npm run test:e2e -w @healthcare-os/web` · `npm run test:e2e:install -w @healthcare-os/web` |
| Viewports | desktop-1280 (1280×800), mobile-390 (390×844, Chromium) |
| Auth env | `PLAYWRIGHT_OWNER_EMAIL` / `PLAYWRIGHT_OWNER_PASSWORD` (optional) |
| Base URL | `PLAYWRIGHT_BASE_URL` default `http://127.0.0.1:3000` |
| API | `NEXT_PUBLIC_API_URL` default `http://127.0.0.1:8000` |

No production credentials. No auth bypass. Cookies remain httpOnly session cookies from real login.

## Commands executed

```text
npx playwright install chromium   # from apps/web
npm run test:e2e -w @healthcare-os/web
```

With Next.js `web:dev` running; API **not** running in this environment.

## Results (this session)

| Project | Public pages | Authenticated owner journey |
|---------|--------------|-------------------------------|
| desktop-1280 | **2 passed** | **skipped** (API down / no owner env) |
| mobile-390 | **2 passed** | **skipped** (API down / no owner env) |

**Totals:** 4 passed · 2 skipped · 0 failed (final green run).

## Screenshots captured

Under `docs/ui-ux/screenshots/`:

- `p31c-desktop-1280-invite.png`
- `p31c-desktop-1280-password-reset.png`
- `p31c-desktop-1280-login.png`
- `p31c-mobile-390-invite.png`
- `p31c-mobile-390-password-reset.png`
- `p31c-mobile-390-login.png`

**Not captured (blocked):** onboarding wizard with live create, practitioner approval after login, staff invite accept E2E, portal enroll E2E, isolation journeys — require API + synthetic credentials.

## Journey status

| Journey | Result |
|---------|--------|
| A Clinic owner (create → approve → dashboard) | UI built; browser **unverified** (API down) |
| B Practitioner pending/approved | UI built; browser **unverified** |
| C Staff invite accept | Public `/invite` **verified** visually; accept API call **unverified** |
| D Patient portal enroll | UI built; browser **unverified** |
| E Isolation | Existing backend tests remain source of truth; browser **unverified** |

## How to complete authenticated verification locally

1. Start API against local Postgres (migrated).  
2. Start `npm run web:dev`.  
3. Seed or signup a synthetic owner; set `PLAYWRIGHT_OWNER_EMAIL` / `PLAYWRIGHT_OWNER_PASSWORD`.  
4. `npm run test:e2e -w @healthcare-os/web`.  
5. Review new screenshots under `docs/ui-ux/screenshots/`.
