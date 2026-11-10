# Application Surfaces

Status: **APPROVED direction; implementation NOT started** (2026-11-08).
Companion: `multi-platform-product-architecture.md`, `client-security-and-distribution.md`.
Inventory verified against `apps/web/**`, `apps/patient-portal/README.md`,
`apps/platform-admin/README.md`, `backend/app/api/v1/*.py`, `packages/ui/*`.

## 1. PUBLIC WEBSITE (new — A1)

Marketing + product/specialty pages, pricing, signup/login, download center, doctor and
patient entry points. Does not exist today (no public route except `/login`).

- REUSE: design tokens/components, signup/verify/login API contracts, onboarding journey
  (signup → clinic → specialty → doctor → trial → workspace), specialty pack content
  (dental reference, ophthalmology discovery — no invented clinical claims).
- MODIFY: none (greenfield, but must share `@healthcare-os/ui` and copy de-gated from
  verification — see frictionless companion).
- NEW: Next.js public app (or route group isolated from authenticated shell — build-time
  decision), SEO/metadata, pricing/download pages, entry routing (doctor → workspace
  setup; patient → portal/PWA/APK guidance). Must not duplicate clinic/portal logic;
  links into the authenticated surfaces only.

## 2. CLINIC APPLICATION — WEB (existing, evolve — A2)

Existing Next.js clinic portal (`apps/web`): reception, patients, schedule, encounters,
dental plans/recalls, billing (invoices/estimates/payments/catalog/receipts), team,
tenant-admin (`/admin` = locations/roles/audit — NOT platform console), sessions,
shell + `NAV`. API via `lib/api.ts` (`credentials:include`, `X-Tenant` selector).

- REUSE: all routes, all backend contracts, session/tenant machinery, RLS, dental/billing
  modules, design system.
- MODIFY: specialty-filtered nav/forms/widgets (hide-only; authorization unchanged),
  verification-optional copy/routing (no lock screens), login routing unverified →
  workspace setup, `GET /tenants/{id}` subscription + specialties display (read-only),
  PWA-safe code hygiene (no `localStorage` secrets — hygiene gate already enforced).
- NEW: `app/workspaces/new` 6-step wizard (O1.2), `lib/specialties.ts` capability filter,
  `specialty_capabilities` read. No clinical logic fork.

## 3. CLINIC APPLICATION — WINDOWS EXE (new — A5, Tauri candidate)

Cloud-connected only. No local clinical database, no offline sync in the initial release.

- REUSE: 100% of clinic web UI + backend contracts + identity/session (Bearer path) +
  tenant/permission/RLS enforcement. The EXE is a packaging of the clinic web surface,
  not a second codebase; all clinical writes go to the same endpoints with the same
  server-side checks.
- MODIFY: web app must be embeddable (relative asset handling, deep-link route support,
  no browser-only assumptions beyond the existing cookie/session model); CORS/origins
  allow-list gains the Tauri origin (tauri-localhost / custom scheme — fixed at spike).
- NEW (spike-gated): Tauri shell, Windows installer/signing, auto-update channel,
  crash/reporting hooks, WebView cookie jar policy (see security companion). Deferred:
  any offline queue, any local DB (SQLite/IndexedDB-as-clinical-store), kiosk/device
  integrations.
- Security note: EXE runs on clinic-managed machines — treat as untrusted client;
  server re-validates everything; no secret baked into the installer.

## 4. PATIENT APPLICATION — WEB + PWA (existing web, PWA new — A3)

Today: `apps/web/app/portal/**` (~13 pages: home, appointments, visits, prescriptions,
dental, billing, documents, access-log) on 24 portal API routes, fenced by
`portal_ctx` + `active_link` + projection rules. PWA: not ready (no manifest, no SW,
`layout.tsx` title-only, no `public/` dir, no `next-pwa`).

- REUSE: portal pages, portal API, link model (`enroll`/`revoke`, unusable-random-password
  + public-reset activation), projection/audit rules, design system.
- MODIFY: add `manifest.webmanifest` + icons + `theme-color`/`appleWebApp` metadata,
  installability without changing auth; patient-only copy ("online payment not available"
  honesty preserved); keep `/portal` vs standalone-app split decision for A3 build
  (`apps/patient-portal/README.md` reserves a separate app + separate auth audience —
  either keep in-`/portal` for v1 or scaffold; do not run both as separate logics).
- NEW: service worker with offline-cache limited to app shell + static assets — NEVER
  clinical data offline store in v1 (same no-offline rule as desktop). Install prompts,
  update flow.

## 5. PATIENT APPLICATION — ANDROID APK (new — A4, Capacitor candidate)

Patient-only functionality over the existing portal API allow-list. No staff routes in
the APK bundle (route-level exclusion + server-side `patient`-role enforcement as
backstop).

- REUSE: portal contracts + link/auth + projection rules + design system. Same backend,
  same database, same eligibility/consent posture.
- MODIFY: API base URL per build flavor (dev/preview/prod), `ALLOWED_ORIGINS` gains the
  Capacitor origin (`https://localhost` default — fixed at spike), auth path verified
  for WebView (HttpOnly cookie jar vs `Authorization: Bearer` — Bearer preferred for the
  APK; both already accepted by `_read_access_token`).
- NEW (spike-gated): Capacitor shell, Play signing/upload, push-notification decision
  (deferred — no provider in O1; reminders stay eligibility-gated), update via Play.
  iOS explicitly deferred — no iOS target, no TestFlight, no App Store work.
- Anti-goal: no separate clinical logic, no staff-mode flag in the APK, no embedded
  secrets, no direct DB access.

## 6. PLATFORM ADMIN (internal — O1.4 + A-series)

Internal platform administration, separate from tenant clinic administration.
Today: `apps/platform-admin/README.md` placeholder (P5 scope) + backend
`platform.py` (`GET /health`, `POST /platform/tenants`) behind `get_platform_admin`
+ `apps/web/app/admin` (tenant locations/roles/audit — clinic-scoped, not platform).

- REUSE: `is_platform_admin` flag gate, audit append pattern, RLS-pinned reads.
- MODIFY: backend gains read-only list/search/detail (+ owners refs + subscription +
  specialties) — additive only, no status mutations, no clinical payloads in O1.4.
- NEW: internal web console (read-only tables, pagination, refs-only display). Never a
  support-bypass: clinical access stays forbidden; support grants (if ever) are explicit,
  time-boxed, audited (W1-adjacent, deferred).

## 7. Surface × capability matrix (APPROVED)

| Capability | Public web | Clinic web | Clinic EXE | Patient web/PWA | Patient APK | Platform admin |
|---|---|---|---|---|---|---|
| Marketing/pricing/download | YES | no | no | no | store listing only | no |
| Signup/login | YES | login only | login only | login only | login only | SSO/internal only |
| Provisioning wizard | link → clinic web | YES | YES (same UI) | no | no | no |
| Clinical/billing/staff | no | YES | YES (same API) | no | no | metadata refs only |
| Portal (own data) | link only | no | no | YES | YES (allow-list) | no |
| Specialty packs | content pages | full UX | full UX | filtered UX | filtered UX | visibility only |
| Offline clinical | no | no | DEFERRED | shell-only cache | DEFERRED | no |

No surface invents permissions; no surface bypasses `require()`/`match_tenant`/RLS/
portal-link checks. Specialty filtering is hide-only on every surface.
