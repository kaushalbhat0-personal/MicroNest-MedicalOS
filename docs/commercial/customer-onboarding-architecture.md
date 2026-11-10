# Customer Onboarding & Commercial Architecture (Discovery)

Status: discovery ONLY. No schema, API, or behavior changes in this slice.
Synthetic data only. Two pilot clinics are prospective customers, not onboarded tenants.

Companions:
- `docs/commercial/subscription-domain-discovery.md` (subscription lifecycle, entitlements, billing separation)
- `docs/commercial/onboarding-journey.md` (target journey, UX flow, two-pilot scenario)

P8.1B notification eligibility is accepted and preserved; P8.1C delivery stays deferred.

## 1. Current implementation inventory

### A. Public website — does not exist

- The web app has exactly one public route: `/login` (email + password sign-in only, no signup link). All other routes are authenticated staff (`/`, `/reception`, `/patients`, `/schedule`, `/encounters`, `/dental/*`, `/billing/*`, `/team`, `/admin`, `/sessions`) or authenticated portal (`/portal/*`). No `middleware.ts`; guards are client-side post-`GET /api/v1/auth/me` 401 redirects.
- Grep over `apps/web` for `signup|register|onboarding|pricing|subscribe` returns zero matches. There is no product page, pricing page, signup, clinic-creation wizard, or checkout. Closest flows are tenant *selection* (dropdown) and portal tenant-picker — both assume an already-provisioned account.
- Implication: the entire acquisition surface (marketing → signup → checkout → provision) must be built. Nothing is reused except the login/session mechanism and the design system.

### B. Identity — login exists, registration does not

- Login/refresh/logout/sessions/password-reset are production-grade: HttpOnly cookies + Bearer fallback, rotation with reuse detection, per-IP and per-account throttles, no-oracle responses (`backend/app/api/v1/auth.py`, `account.py`).
- **No public registration endpoint exists** (grep for signup/register in `backend/app` is empty). Users enter the system three ways only: (1) `ops bootstrap` creates the first platform admin + first tenant + location + tenant_admin membership; (2) staff invite accept (`POST /api/v1/invites/accept`) creates a user + membership from a 256-bit capability token (7-day TTL, role-bound, tenant-activation checked); (3) portal enrollment creates a portal-only user with an unusable random password, activated via the public password-reset flow.
- Duplicate handling: `create_user` raises on duplicate email; `accept_invitation` reuses an existing user for a second tenant (sets password) — the multi-tenancy primitive already works.

### C. Tenancy — operator-driven, sound primitives

- `tenancy.create_tenant` (slug unique, status active), `clinics.create_location` (name-unique-per-tenant; **timezone stored as an unvalidated string**, default `Asia/Kolkata`), `create_membership` (one user+tenant row, `ConflictError` on duplicates), seed roles + tenant custom roles (subset-only, `PLATFORM_ONLY` blocked).
- Last-admin protection exists with ordered row locks against write-skew (`update_membership`). Location scope is relational (`membership_locations`), never JSON. Tenant switching is explicit `X-Tenant` selection; missing/foreign selector fails closed (403/404 anti-oracle via `match_tenant`).
- Tenant creation is platform-admin-only (`POST /platform/tenants`) or operator CLI. **There is no self-service path and no ownership record**: the bootstrap membership is `is_primary` but nothing distinguishes a billing owner from an admin. Tenant suspension exists (`set_tenant_status`) and invite-accept already refuses inactive tenants — the enforcement hook for subscription gating is present but unwired.

### D. Practitioner and staff — verified, tenant-scoped

- `Practitioner` is optionally linked to a user (visiting doctors have none). Verification is per `(tenant, practitioner)` with pending/approved/rejected states; scheduling refuses unverified practitioners. Roles assign location scope at membership creation; role changes re-validate locations server-side. Staff invites carry email + role, throttled per inviting user, and emit a `staff_invite` notification request.

### E. Clinic setup — partial

- Exists: locations (name + timezone + active flag), practitioner profiles + verification, service catalog (charge master), appointment settings embedded in scheduling (durations, double-book guard, idempotency). Missing: clinic display profile beyond tenant name, specialty selection (no specialty field anywhere — dental vs ophthalmology is purely module usage today), working hours (no model), services-to-specialty linkage, branding storage/resolution (stub only, `branding.manage` permission defined).

### F. Subscription — stubs only

- `subscriptions/__init__.py`, `licensing/__init__.py`, `branding/__init__.py` are one-line docstrings each. No tables, routes, plans, entitlements, or payment code. Single sentence of licensing policy exists: "offline grace (reads never locked)".

### G. Patient portal — included feature, correctly fenced

- Enrollment is staff-gated (`STAFF_MANAGE`), binds one `(tenant, user)` to one patient, reactivates instead of duplicating, revokes fail-closed; all portal reads resolve `patient_id` server-side from the active link. Portal users are plain users with the `patient` role bundle (`portal.read`, `portal.appointment.cancel`). No separate patient subscription exists anywhere — matches the locked business model.

### H. Platform administration — minimal

- `is_platform_admin` flag + `GET /platform/health` + `POST /platform/tenants`. No tenant list/search, no status management endpoint, no subscription visibility, no support-access flow (`support.grant` permission is defined but the granting flow is deferred). The `/admin` web page is a *tenant* admin surface (locations/roles/audit), not a platform console.

### I. Billing separation — clean clinic billing, no platform billing

- Clinic billing (P4) is complete and isolated: Decimal-only `Money` (INR-only policy, float rejected), FY doc numbers, idempotency keys, estimate→invoice→payment/allocation→receipt/refund/credit-note state machines, tenant + location scoping (`backend/app/modules/billing/`). Nothing in it references plans, seats, or subscriptions. The `Money` arithmetic functions are pure and reusable; the tables and state machines must never be shared with subscription billing.

### J. Deployment — P7 profiles, Docker retained

- `ENV × DEPLOYMENT` boot validation, same containers for cloud/private/on-prem (P7-01), preview compose retained. Deployment licensing is declared separate from subscriptions. No changes in this slice.

## 2. Proposed domain boundaries

| Domain | Owns | Must never |
|---|---|---|
| Platform identity | users, credentials, sessions, password reset | carry tenant_id |
| Tenant ownership | tenant row, ownership/subscription linkage, status | read clinical rows |
| Clinic membership | memberships, roles, location scope, verification | mint entitlements |
| Practitioner identity | practitioner rows, per-tenant verification | act as login |
| Subscription account | plan, seats, status, lifecycle, grace | touch clinical/billing tables |
| Subscription billing | platform invoices/receipts for SaaS fees | reuse clinic invoice tables |
| Clinic billing (existing) | patient charges, estimates, invoices, payments | reference subscriptions |
| Patient portal (existing) | links, projections, cancellation | become a paid SKU |
| Deployment license | on-prem/private entitlement, offline grace | gate SaaS features |

Cross-domain links are by id reference only, checked server-side. The audit log records all ownership/subscription transitions (refs only).

## 3. Tenant ownership model (proposed default)

- Add an ownership record on the tenant: `owner_user_id` (the purchasing doctor) plus `billing_email`, set at provisioning from the authenticated signup session — never from client-supplied ids. The `is_primary` membership flag is a UX hint, not the ownership authority.
- One doctor MAY own multiple clinics (one user, N owner memberships). A doctor MAY belong to another clinic as visiting practitioner (second membership + that tenant's verification; practitioner row optionally shared via `user_id`). A clinic MAY have multiple owners/admins; last-admin protection extends to last-owner protection.
- Ownership transfer: explicit action by current owner or platform admin, audited. Deactivating the owner's user does not delete the tenant.
- These are proposed defaults; each needs product-owner approval (see §7).

## 4. Account and invitation model

- Signup creates a platform identity (verified email) with zero memberships. Clinic workspace creation is a separate, authenticated step that simultaneously creates tenant + location + owner membership + subscription account in one transaction (atomic provision; failure rolls back everything).
- Staff invites are unchanged in mechanism, with two additions: invites cannot be issued for (or accepted into) a tenant whose subscription is not in an operating state (decision: block at invite vs block at accept — recommend block at accept so outstanding invites survive brief grace periods, pending approval); invite role assignment stays subset-validated.
- Portal enrollment stays staff-gated and subscription-independent for reads (see §6); new enrollments are blocked when the clinic subscription is suspended (proposed, needs approval).

## 5. Existing functionality to reuse (do not rebuild)

AuthN/session/rate-limit/no-oracle patterns; `create_tenant`, `create_location` (+ add IANA validation), membership/role/location-scope machinery, last-admin guard pattern; invite capability-token flow; practitioner verification; portal link model; audit append/verify; outbox for onboarding side-effects (welcome notifications post-P8.1C); P7 config profiles; `Money` pure functions; design tokens/components; tenant/location isolation tests as the template for subscription isolation tests.

## 6. Missing capabilities (ranked)

1. Public site + signup + email verification + checkout + atomic provision (the whole acquisition funnel).
2. Subscription tables/service/entitlement checks + platform billing tables (see companion doc).
3. Specialty selection, working hours, clinic profile, branding storage/resolution.
4. Platform console (tenant list, status, subscription visibility, support access).
5. Owner-before-subscribe policy, grace/suspension enforcement points, export flow.
6. Onboarding progress tracking and staff/patient import tooling.

## 7. Product decisions requiring approval

D1 owner-before-subscribe: can an owner invite staff before paying? D2 grace terms: duration, read-only vs full operation during grace, portal behavior. D3 expiry semantics: portal reads preserved (recommended: yes, clinical-safety rule), writes blocked, new enrollments blocked. D4 data retention + export format/availability after expiry/cancellation. D5 suspension without data destruction (recommended: always; status-gate only). D6 plan-change proration, location/practitioner/seat limits per plan, specialty enablement per plan. D7 visiting-doctor billing identity (which clinic's subscription covers their actions). D8 support-access UX and consent. D9 trial terms. D10 refund policy for SaaS fees.

## 8. Recommended implementation phases

- **O1**: public site shell + signup + email verification + atomic provision (tenant+location+owner+subscription-trial) + platform console read views. Unblocks synthetic pilot onboarding end-to-end (trial, no payment).
- **O2**: subscription plans/lifecycle/entitlement enforcement + checkout (test-mode payments) + grace/suspension + export.
- **O3**: clinic setup completion (specialty, hours, profile, branding resolution), staff/patient import, onboarding progress UX.
- **O4**: production payment collection, invoicing, dunning, plan changes, support access.

## 9. Test strategy

DB-backed serial suites mirroring existing isolation tests: synthetic two-pilot onboarding (independent tenants/memberships/patients/billing/portal/audit), cross-tenant subscription probes (404/403), entitlement bypass attempts, invite-before-subscribe policy, grace/expiry behavior (reads preserved, writes blocked), export completeness, ownership transfer, last-owner protection. Unit suites for lifecycle state machine and entitlement evaluation. No live payments, no real PII, preview/test DBs only.
