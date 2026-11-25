# P3.2 — Visual QA

**Scope:** Authenticated synthetic sessions only. No wholesale redesign.  
**Viewports:** 1440×900 · 1280×800 · 390×844  
**Screenshots:** `docs/ui-ux/screenshots/p32-*.png` (48 files)

## Capture matrix

| Surface | 1440 | 1280 | 390 |
|---------|------|------|-----|
| Login / invite / password-reset (public) | ✓ | ✓ | ✓ |
| Workspace onboarding | ✓ | ✓ | ✓ |
| Workspace created | ✓ | ✓ | ✓ |
| Practitioner pending / approved | ✓ | ✓ | ✓ |
| Clinic dashboard | ✓ | ✓ | ✓ |
| Patient directory | ✓ | ✓ | ✓ |
| Schedule | ✓ | ✓ | ✓ |
| Reception | ✓ | ✓ | ✓ |
| Staff invitation (directory) | — | ✓ | — |
| Invite accepted (post-redirect) | — | ✓ | — |
| Patient 360° / enroll | — | ✓ | — |
| Patient portal | — | ✓ | — |
| Portal unauthenticated | — | ✓ | — |

## Review findings

| Area | Finding | Action |
|------|---------|--------|
| Alignment / spacing | Shell + PageHeader consistent with P3.1 design tokens | None |
| Typography / hierarchy | Clinic titles readable; helpers secondary | None |
| Mobile 390 | Patients / schedule usable; hamburger shell intact | None |
| Overflow | No horizontal overflow observed on captured pages | None |
| Loading | Dashboard capture could land on “Loading workspace…” mid-fetch | Test wait added before dashboard screenshot |
| Error states | Invite invalid/expired Alert present | Verified in e2e |
| Accessibility | Headings, labeled fields, progress list retained | No new regressions found |
| Tokens in screenshots | Invite accept docs shots taken after redirect only | Policy followed |

## Low-risk UX fixes this phase

- `allowedDevOrigins` for `127.0.0.1` / `localhost` so Playwright does not fight Next HMR host checks.
- Align `NEXT_PUBLIC_API_URL` hostname with the page origin so session cookies work (`localhost` ↔ `localhost`).
- No visual redesign of clinic workflows.

## Residual visual notes (non-blocking)

- Floating “N” badge in some captures is an external overlay (not product UI).
- Empty patient directory on brand-new workspaces is expected for synthetic owner journeys.
