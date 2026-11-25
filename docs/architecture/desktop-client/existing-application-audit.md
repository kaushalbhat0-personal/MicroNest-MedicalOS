# Existing application audit (Phase 1.1)

**Evidence date:** 2026-11-25  
**Repo:** `release/p3-7b-staging` @ `293dc66` (+ local uncommitted proxy/docs/experiments preserved)  
**Stacks verified:** Next `^16.4.6`, React `19.0.0`, Tailwind `^4.3.4`, FastAPI modular monolith, Playwright `^1.51.1`, Vitest `^4.1.12`

Status legend for UI: **exists** | **partial** | **missing** | **future**

---

## 1. Shell, design, and shared UI

| Item | Evidence | Status |
|------|----------|--------|
| DESIGN.md | Repo root — clinic compact density, portal comfortable, WCAG 2.2 AA | Source of truth |
| `packages/ui` | Tokens, AppShell, PageHeader, tables, healthcare, dental, imaging | Reusable without Next |
| Clinic shell | `apps/web/app/shell.tsx` + `packages/ui/navigation.tsx` | exists |
| Nav + RBAC filter | `apps/web/lib/nav.ts` (`NAV`, `NAV_RULES`, `filterNavByPermissions`) | exists |
| Portal shell | `apps/web/app/portal/shell.tsx`, `lib/portal.ts` | exists (patient) |
| API client | `apps/web/lib/api.ts` (+ uncommitted same-origin proxy helpers) | Cookie/`credentials` web path |

---

## 2. Feature inventory (clinic staff)

For each feature: implementation status, API, permission, UI, desktop suitability, missing work, tests.

### 2.1 Overview

| Feature | Impl | API (representative) | Permission | UI | Desktop suitability | Missing / notes | Tests |
|---------|------|----------------------|------------|-----|---------------------|-----------------|-------|
| Dashboard | exists | appointments + workspace context via page fetches | always shown in nav | `/` | High — metrics + today list | Deep analytics **future** | Playwright journeys, P3.3 |
| Setup / onboarding | exists | workspaces, practitioners, invites | open to signed-in clinic users | `/onboarding` | Medium | — | Playwright extensive |
| Operations day board | exists | `GET .../operations-dashboard` | any of appointment/followup/billing/staff.manage + feature flag | `/operations` | High workstation board | — | Vitest `operations/page.test.tsx`, P3.3 |

### 2.2 Patient care

| Feature | Impl | API | Permission | UI | Desktop | Missing | Tests |
|---------|------|-----|------------|-----|---------|---------|-------|
| Patient directory / search | exists | `/tenants/{id}/patients*` | `patient.read` | `/patients` | High | — | Playwright |
| Patient registration | exists | `patient.create` | `patient.create` | `/patients` | High | — | Playwright |
| Patient 360 | exists | overview, timeline, related | `patient.read` (+ clinical/billing as used) | `/patients/[id]` tabs | **Primary desktop surface** | — | Playwright P3.2/P3.3 |
| Follow-ups | exists | follow-up routes under communications | `followup.read` / `followup.manage` | `/follow-ups` | High | — | P3.3 |
| Patient communication log | exists (web) | communications APIs | `communication.*` | primarily via patient/follow-up flows | Medium | Dedicated inbox **partial/future** | limited |
| CSV import | exists | patients import path in UI | patient create/update | `/patients` | High | — | — |

### 2.3 Scheduling & reception

| Feature | Impl | API | Permission | UI | Desktop | Missing | Tests |
|---------|------|-----|------------|-----|---------|---------|-------|
| Calendar day/week/month | exists | scheduling appointments | `appointment.read` | `/schedule` | High | — | Playwright |
| Book / reschedule / cancel | exists | appointment create/update | `appointment.create` / `update` | `/schedule` | High | — | Playwright |
| Walk-ins / status | exists | appointment status | `appointment.update` | schedule + reception | High | — | — |
| Reception queue | exists | `.../reception-queue` | **`appointment.read`** (not `queue.manage`) | `/reception` | High multi-column | `queue.manage` declared unused | Playwright |
| Check-in / complete | exists | status transitions | `appointment.update` | `/reception` | High | — | — |
| Working hours / availability | exists | locations hours, staff availability | `locations.manage` / `appointment.read` | schedule + admin | High | — | — |

### 2.4 Clinical

| Feature | Impl | API | Permission | UI | Desktop | Missing | Tests |
|---------|------|-----|------------|-----|---------|---------|-------|
| Encounter list | exists | encounters list | `encounter.read` | `/encounters` | High | List lacks PageHeader polish | P3.3 |
| Consultation workspace | exists | open/close, notes, vitals, dx | encounter + clinical perms | `/encounters/[id]` | **Primary doctor surface** | — | docs-tab Vitest, P3.3 |
| Prescriptions | exists | prescriptions module | `prescription.read/create/sign` | encounter tabs | High | Standalone Rx queue **partial** | — |
| Treatment plans | exists | dental plans | `dental.read` / `plan.manage` | `/dental/plans`, `[id]` | High | Patient ID entry UX weak | P3.3 |
| Dental charting | exists | dental conditions + Odontogram UI | `dental.record` / read | encounter dental tab | High | — | P3.3 |
| Recalls | exists | dental recalls | dental perms | `/dental/recalls` | Medium | **Not in sidebar** | — |
| Clinical documents / imaging | exists | document refs + ClinicalImageViewer | dental/clinical paths (not `documents.*` require) | encounter docs tab | High | `documents.*` perms unused on routes | Vitest imaging |

### 2.5 Clinic operations

| Feature | Impl | API | Permission | UI | Desktop | Missing | Tests |
|---------|------|-----|------------|-----|---------|---------|-------|
| Invoices | exists | billing invoices | `billing.read`, issue/create | `/billing/invoices*` | High | — | P3.3 |
| Estimates | exists | estimates | billing create/read | `/billing/estimates*` | High | Not in sidebar | P3.3 |
| Payments / allocations | exists | payments | `payment.record` | `/billing/payments` | High | Not in sidebar | — |
| Catalog | exists | service catalog | `billing.config` / read | `/billing/catalog` | High | Not in sidebar | — |
| Receipts | partial | receipts | billing/payment | `/billing/receipts/[id]` | Medium | Thin read-only UI | — |
| Inventory (items, stock, PO, suppliers) | exists | inventory module | inventory.* | `/inventory` tabs | High | — | none found |
| Outstanding balances | partial | via invoices/patient billing | `billing.read` | invoice + patient tabs | High | Dedicated AR aging **future** | — |

### 2.6 Workforce

| Feature | Impl | API | Permission | UI | Desktop | Missing | Tests |
|---------|------|-----|------------|-----|---------|---------|-------|
| Staff directory / HR hub | exists | staff APIs | `staff.manage` / invite | `/staff` (7 tabs) | High | — | Playwright invite |
| Team membership + invite | exists | invites + memberships | staff.manage/invite | `/team` | Medium | **Overlaps `/staff`** | Playwright |
| Roles | exists | tenant roles | `roles.manage` | admin + staff | High | — | — |
| Practitioners | exists | practitioner admin | staff.manage | admin/onboarding | High | — | Playwright |
| Attendance / leave / schedules | exists | staff attendance/leave/schedules | tenant.read self / staff.manage | `/staff` tabs | High | — | — |

### 2.7 Workspace / settings

| Feature | Impl | API | Permission | UI | Desktop | Missing | Tests |
|---------|------|-----|------------|-----|---------|---------|-------|
| Clinic settings | exists | locations, roles, audit, practitioners | settings/roles/locations/audit (nav anyOf) | `/admin` | High | `settings.manage` **no API require()** yet | Playwright admin smoke |
| Subscription / plans | exists | subscriptions + plans | subscription.read | `/subscription`, `/plans` | Medium | SaaS frozen for product changes | — |
| Sessions | exists | `/auth/sessions` | authenticated | `/sessions` | High for security UX | — | — |
| Notifications center | missing | — | — | — | — | **future** | — |
| Platform tenants | exists | `/api/v1/platform` | `is_platform_admin` | `/platform/tenants*` | Out of clinic EXE MVP | Not in clinic nav | — |

### 2.8 Auth (web)

| Feature | Impl | API | UI | Desktop note | Tests |
|---------|------|-----|-----|--------------|-------|
| Login / logout / me | exists | `/api/v1/auth/*` cookies | `/login` | **Native needs JSON tokens** | Playwright |
| Signup / verify / reset / invite | exists | auth + invites | respective routes | Web/onboarding; desktop may deep-link later | Playwright |

---

## 3. Backend module map (clinic-relevant)

Mounted under `/api/v1` (`backend/app/api/v1/router.py`): auth, account, invites, signup, platform, tenants, workspaces, subscriptions, saas_payments, audit, patients, communications, scheduling, encounters, prescriptions, dental, billing, inventory, staff, operations, portal.

**Seed roles** (`permissions.py`): `platform_admin`, `tenant_admin`, `doctor`, `receptionist`, `nurse`, `accountant`, `staff`, `patient`.

**Declared but unused on API routes (grep):** `settings.manage`, `schedule.manage`, `queue.manage`, `documents.read/upload`, `branding.manage`, `reports.view/export` (and platform.* not used via `require()` — platform uses `is_platform_admin`).

**Server `outbox_events`:** transactional worker relay — **not** a device sync outbox.

---

## 4. Patient portal (boundary summary)

Routes under `/portal/*` with separate shell — see [patient-pwa-boundary.md](./patient-pwa-boundary.md). Not part of clinic desktop EXE.

---

## 5. Tests inventory

| Layer | Location | Coverage notes |
|-------|----------|----------------|
| Playwright | `apps/web/e2e/` | desktop-1440, desktop-1280, mobile-390; onboarding, auth journeys, P3.3 visuals; fails if API down |
| Vitest | `apps/web/lib/**/*.test.ts`, some app tests | nav RBAC, operations page, docs-tab, clinical-viewer, apiBase (uncommitted) |
| Backend | existing module/security suites (staging P3.7C isolation scripts) | synthetic tenants |

Desktop EXE will need **new** Playwright/WebDriver or Tauri WebDriver suite — web E2E does not prove EXE.

---

## 6. Native experiments (do not delete)

| Artifact | Finding for Phase 1.1 |
|----------|----------------------|
| A2 DPAPI PoC | Credential-wrap pattern **PASS** — reuse for refresh token storage (not patient DB in v1) |
| A2 Tauri shell | **NOT IMPLEMENTED** |
| A3 device/lease/outbox | **NOT IMPLEMENTED** — not required for online-first v1 beyond optional device binding |
| Mock API | PoC-only; **must not** substitute production auth in implementation phases |

---

## 7. Audit conclusions

1. Clinic operational surface is largely **implemented** on web; desktop is primarily a **host + auth + packaging** problem, not greenfield clinical features.  
2. Highest-value reuse: Patient 360, encounter workspace, schedule/reception, billing invoice detail, staff, operations.  
3. IA cleanup for desktop: merge Team/Staff clarity; surface estimates/payments/catalog/recalls in nav.  
4. Hard blocker for EXE login: production auth is **cookie-first**; refresh is **cookie-only**.  
5. Online-first v1 can ship without offline DB; keep `SecureCredentialStore` abstraction for later offline phase.
