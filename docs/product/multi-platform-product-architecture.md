# Multi-Platform Product Architecture

Status: **APPROVED direction; implementation NOT started** (architecture alignment, 2026-11-08).
Companions: `application-surfaces.md`, `client-security-and-distribution.md`,
`../roadmap/healthcare-os-product-roadmap.md`, `../commercial/o1-revised-implementation-plan.md`.
Sources inspected: `apps/web/**`, `apps/patient-portal/README.md`,
`apps/platform-admin/README.md`, `packages/ui/*`, `DESIGN.md`,
`backend/app/main.py`, `backend/app/api/**`, `backend/app/modules/{dental,portal}/**`,
`backend/Dockerfile`, `apps/web/Dockerfile`, `infrastructure/preview/*`, `docs/commercial/*`,
`docs/specialties/*`, `docs/pilots/*`.

Preservation: docs only. No code, migration, Docker/Compose/CI, dependency, DB change.
Do NOT add Tauri or Capacitor dependencies in this slice (future implementation spike only).

## 0. Git baseline

- Branch: `main`, HEAD: `efefb0a3b31ff3c32a090506961d6f875a51b612`.
- This slice creates/updates docs only. No reset, clean, stash, discard, commit, push.

## 1. APPROVED decisions (binding)

1. One generic multi-specialty Healthcare OS; one shared backend (FastAPI + PostgreSQL).
2. Doctor/clinic is the paying customer. Patient portal is included, never a separate SKU.
3. Frictionless onboarding (signup → clinic → specialty → doctor → trial → workspace);
   no mandatory email verification; verification retained as optional security.
4. 14-day trial, no card, no automatic charge; trial row atomic with provisioning.
5. Clinic desktop = Windows EXE, cloud-connected only (Tauri candidate, spike-gated).
6. Patient mobile = Android APK first (Capacitor candidate, spike-gated); iOS deferred.
7. Patient browser + PWA remain available alongside the APK.
8. Marketing frontend is the public entry point for doctors and patients.
9. Communications = platform email + optional BYO email + WhatsApp Web manual handoff +
   authorized WhatsApp API providers incl. WATI; comms config skippable.
10. Specialty-aware experience for dental + ophthalmology via registry packs; packs
    configure workflows, never security.
11. No offline sync and no local clinical database in the initial desktop release.
12. Docker support stays intact; no Docker/Compose/CI architecture change in this slice.

## 2. Application inventory (what exists — verified)

| Surface | Location | State |
|---|---|---|
| Clinic web app | `apps/web` (Next.js 16, React 19, monorepo workspace `@healthcare-os/web`) | Built: ~35 routes — `/login /signup /verify /reception /patients[/[id]] /schedule /encounters[/[id]] /dental/plans[/[id]] /dental/recalls /billing/{invoices,estimates,payments,catalog}[/...] /team /admin /sessions`, plus patient portal under `/portal/**` (~13 pages). Libs: `lib/api.ts` (cookie fetch + `X-Tenant`), `lib/tenant.ts` (localStorage selector only), `lib/nav.ts`, `lib/portal.ts`, `lib/use-api.ts`. No PWA (no manifest/SW; `layout.tsx` title-only). Dockerfile: 2-stage `node:22-alpine`, non-root, `EXPOSE 3000`. |
| Patient portal (web) | `apps/web/app/portal/**` + `backend/app/api/v1/portal.py` (24 routes) + `modules/portal/service.py` | Built, correctly fenced: staff-gated enroll/revoke (`P.STAFF_MANAGE`), `active_link`/`resolve_patient_id` choke point, projection rules (closed-encounter finalized-only, signed-Rx-only, issued-financials-only, metadata-only documents). Separate `patient` seed role. |
| Patient portal (standalone) | `apps/patient-portal/README.md` only | Placeholder: "Separate Next.js app, separate auth audience, portal allow-list APIs only. Not scaffolded in P1." Genuinely new. |
| Platform admin | `apps/platform-admin/README.md` only + `backend/app/api/v1/platform.py` (2 routes: `GET /platform/health`, `POST /platform/tenants`) + `apps/web/app/admin` (tenant admin, NOT platform console) | Placeholder + minimal API. Genuinely new console; additive read views only in O1.4. |
| Marketing website | Does not exist | Genuinely new (A1). Discovery notes the whole acquisition surface must be built. |
| Desktop EXE / Android APK | Do not exist; zero Tauri/Capacitor/Electron deps repo-wide (grep over `*.json` clean; npm workspaces = `apps/web` + `packages/*`) | Genuinely new; candidates named only (A4/A5). |
| Design system | `packages/ui/*` (`Button/fields/feedback/overlays/data/navigation/healthcare/dental/tokens/theme/components`) + `DESIGN.md` (22 sections) | Built, single system. Reused by every surface. |
| Backend API | `backend/app` FastAPI, 14 routers, `GET /api/healthz|readyz`, `/api/docs`, CORS explicit-origins + credentials, security headers | Built. Shared by all clients (see §3). |
| Identity/session | `modules/identity/*` + `platform/security/{cookies,tokens}` + `api/deps.py` | Built: HttpOnly cookies + Bearer fallback (native-ready), JWT access (10 min) + rotating opaque refresh (SHA-256, family + reuse detection), server-derived tenant ctx, portal-link binding, optional verification. |
| Specialty modules | `modules/dental/*` (8 tables, FDI/P3 rules) + `docs/specialties/ophthalmology-discovery.md` (discovery only) | Dental built; eye genuinely new module (post-sign-off). |

## 3. Final application architecture (APPROVED)

```
                    ┌─ Marketing website (A1, Next.js) ─ public
                    │
                    ├─ Clinic web app (existing apps/web) ─ authenticated staff
  Doctors/patients ─┤
                    ├─ Clinic desktop EXE (A5, Tauri cand.) ─ authenticated staff, cloud-only
                    │     (same web UI served/packaged; NO local clinical DB; NO offline sync v1)
                    ├─ Patient web + PWA (A3: existing /portal + manifest/SW)
                    ├─ Patient Android APK (A4, Capacitor cand.) ─ patient-only APIs
                    └─ Platform admin console (O1.4/A-series: read-only web)

  ALL surfaces ─▶ ONE FastAPI backend ─▶ ONE PostgreSQL (RLS) ─▶ S3-compatible storage
  Identity: shared users/sessions; Bearer fallback already accepted (cookies.py).
  Tenant ctx: always server-derived (get_ctx / portal_ctx). No client permissions.
```

- One shared backend: no per-client API fork, no separate clinical logic for EXE/APK.
  Native shells render the same contracts; capability differences are enforced server-side
  by role + portal-link + permission, never by "which app called".
- Shared API contracts: OpenAPI (`/api/openapi.json`) is the single contract; web/APK/EXE
  code-generate or hand-track the same shapes (`Me`, `TenantOption`, portal projections).
- Shared design system: every surface uses `@healthcare-os/ui` tokens/components; brand
  override limited to `--hos-brand-*` (white-label W1 builds on this later).
- Specialty packs configure workflows (terminology, nav, forms, widgets, templates,
  shortcuts) uniformly across web/EXE/APK; they never alter identity, tenancy,
  permissions, RLS, or eligibility (specialty companion governs).

## 4. Reuse vs new (summary; detail in `application-surfaces.md`)

- Reuse as-is: backend routers, identity/session + Bearer fallback, `get_ctx`/`portal_ctx`,
  RLS policies, eligibility gate, dental module, billing module, design system, Docker images.
- Modify: `apps/web` (public/marketing split, PWA manifest/SW, specialty-filtered nav,
  copy de-gating verification), backend read views (subscription/specialty/capabilities,
  platform list/detail — additive only), CORS origins per deployed surface.
- Genuinely new: marketing site, standalone patient-portal app scaffolding (or keep
  `/portal` + PWA and defer split — A3 decision), platform-admin console, Tauri EXE
  packaging, Capacitor APK packaging, ophthalmology module, comms provider adapters.
  None built in this slice.

## 5. Non-goals in this slice

Tauri/Capacitor dependencies, scaffolding, store/packaging work, PWA service worker,
ophthalmology tables, comms providers, enforcement gates, Docker/CI changes — all deferred
to roadmap slices with their own spikes and sign-offs.
