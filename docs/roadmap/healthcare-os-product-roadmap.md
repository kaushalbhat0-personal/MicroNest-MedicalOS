# Healthcare OS Product Roadmap

Status: **APPROVED structure; slices NOT started** (architecture alignment, 2026-11-08).
Companions: `../product/multi-platform-product-architecture.md`,
`../product/application-surfaces.md`, `../product/client-security-and-distribution.md`,
`../commercial/o1-revised-implementation-plan.md` (governing for O1),
`../commercial/frictionless-onboarding.md`, `../commercial/specialty-pack-architecture.md`.
No code/migration/dependency in this slice.

Legend: MUST = release-blocking gate. SHOULD = expected unless waived with reason.
Each slice is a separate implementation unit with its own tests and rollback note.

## O1 track — commercial onboarding (governing detail in `o1-revised-implementation-plan.md`)

- **O1.1.1 Frictionless identity alignment (docs + copy/routing, no schema).**
  Remove verification as a provisioning requirement everywhere (code already complies —
  `require_verified_email` has zero production callers; keep it for progressive assurance
  only). Reword signup/verify/login routing so no screen implies a lock. MUST: existing
  `test_signup_api.py` suite green; gate test updated to assert the helper is NOT called
  by provisioning. No migration, no provider, no enforcement.
- **O1.2 Atomic provisioning + trial record (one release train).**
  Migrations (`tenant_owners`, `subscription_plans`+`subscriptions`+seed `trial-14d`,
  `tenant_specialties`+`location_specialties`, `workspace_provisions`), IANA validation,
  `POST /workspaces` (idempotent, all-or-nothing, owner=caller, trial insert, specialty
  rows, audit/outbox refs). MUST: atomicity/fault-injection, idempotency matrix,
  validation matrix, double-provision independence, unverified-provision allowed,
  unauth 401, trial-row-exists + negative-enforcement, new-table RLS tests.
- **O1.3 Subscription and entitlements (foundation, read-only visibility).**
  Subscription/specialty/capability reads; seed uniqueness; billing-separation schema
  test. MUST (negative): zero enforcement interlocks — clinical/portal/billing/invite/
  audit behave identically with/without (incl. expired-fixture) trial rows. No gateway.
- **O1.4 Platform administration (read-only).** List/search/detail (+ owners,
  subscription, specialties), pagination, audit, 403 non-admin. MUST: no mutations,
  no clinical payloads, refs-only display.
- **O1.5 Two-pilot validation.** Synthetic Nevase-dental + independent-eye provision via
  signup→workspaces; isolation matrix (extends `test_p8_two_tenant_pilots.py`); cross
  probes 403/404. MUST: `ruff+mypy+pytest`, single head, migrate review, preview smoke,
  Docker images build (no Compose/CI architecture change).

## A track — application surfaces

- **A1 Public website.** Marketing/product/specialty pages, pricing, signup/login,
  download center, doctor/patient entries. Depends on O1.1.1 copy contracts.
  MUST: shares `@healthcare-os/ui`, no duplicated clinic/portal logic, SEO/metadata,
  no secrets in bundle.
- **A2 Clinic workspace UX.** Workspaces wizard, specialty-filtered shell (hide-only),
  verification-optional routing. Depends on O1.2. MUST: authorization unchanged
  (route-filter tests), WCAG 2.2 AA, mobile-first.
- **A3 Patient portal PWA.** Manifest/icons/metadata + shell-only service worker
  (never PHI caching) over existing `/portal` + decision on
  `apps/patient-portal` split (keep-in-`/portal` for v1 recommended). MUST: installable,
  logout clears cache, no clinical offline store.
- **A4 Android APK (Capacitor candidate).** Spike first: WebView auth (Bearer-preferred),
  `ALLOWED_ORIGINS`, secure storage, Play signing, patient-only allow-list + server
  backstop. MUST: no staff routes in bundle, no embedded secrets, `allowBackup=false`,
  `minApiVersion` floor honored. Depends on A3 portal maturity.
- **A5 Windows EXE (Tauri candidate).** Spike first: packaging of clinic web UI,
  installer signing, signed updater, minimal capabilities, OS token storage.
  Cloud-connected only; local clinical DB + offline sync explicitly deferred.
  MUST: same contracts, same server checks, no baked secrets. Depends on A2.
- **A6 Cross-platform release validation.** Backend→web→native build order, contract
  floor checks, store/installer staged rollout, rollback runbook. MUST: compatibility
  matrix green (web + EXE + APK against one preview backend), telemetry contains zero
  tokens/PHI.

Spike rule (A4/A5): evaluate Tauri/Capacitor in a throwaway spike BEFORE committing.
No framework dependency lands in `package.json`/workspaces until the spike report is
approved. This slice adds none.

## Capability tracks

- **S1 Specialty engine.** Registry + enablement rows (shipped in O1.2) → dental pack
  codified as-is → ophthalmology module built only after discovery sign-off (no invented
  clinical rules). MUST: packs configure, never authorize; hide-only filtering tests.
- **C1 Communications integrations.** Platform email provider first, then BYO email,
  then WATI/BSP adapters per `communications-architecture.md`. Comms stay skippable
  through O1–A. MUST: encrypted creds, tenant isolation, eligibility-first dispatch,
  refs-only audit/metering, no equivalence between Web handoff and API delivery.
- **W1 White-label.** Brand resolver (`--hos-brand-*` + per-tenant assets), domain
  strategy, tenant-scoped theming over the single design system. Deferred until A1/A2
  stable. MUST: appearance-only (never authorization/behavior fork), no per-tenant code.

## Ordering and dependencies

```
O1.1.1 → O1.2 → O1.3 → O1.4 → O1.5
           ↓
     A1 ──→ A2 ──→ A5 ──→ A6
      ↓       ↓
     A3 ──→ A4 ──→ A6
S1 rides O1.2 (enablement) then grows per specialty sign-off.
C1 and W1 start after O1.5 (platform email may pull earlier only with sign-off).
```

## Deferred (explicit, all tracks)

Payment gateway/dunning/proration, metering enforcement, iOS app, offline sync,
local clinical DB, push provider, MDM/kiosk, portal SKU, support-bypass, prod data
access, Docker/CI architecture changes. Each needs owner sign-off + threat review.
