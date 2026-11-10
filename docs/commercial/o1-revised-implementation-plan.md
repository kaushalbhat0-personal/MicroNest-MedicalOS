# O1 Revised Implementation Plan (Frictionless Onboarding)

Status: **APPROVED direction; implementation NOT started** (architecture alignment, 2026-11-08).
Replaces the provisioning/verification contracts in `o1-implementation-plan.md` §§6–9,
`o1-security-and-data-model.md` §§3–4, and `o1-acceptance-criteria.md` O1.1/O1.2 gates
where they conflict. The three prior docs remain for history; this plan governs.
Companions: `frictionless-onboarding.md`, `specialty-pack-architecture.md`,
`communications-architecture.md`.

Preservation: docs only. No migration, code, Docker/Compose/CI, DB write, commit/push.

## 0. Git baseline

- Branch: `main`, HEAD: `efefb0a3b31ff3c32a090506961d6f875a51b612`.
- Pre-existing modified/untracked work preserved untouched. This slice adds/updates only
  `docs/commercial/*`.

## 1. Verdict

**Proceed to implementation in the sequence in §9.** The frictionless direction is
compatible with the existing O1.1 code: verification was never wired as a provisioning
gate, login/reset/invite flows already work unverified, and duplicate/normalization/
no-oracle properties hold. The remaining work is additive: one atomic provisioning
transaction (+ trial row), IANA validation, idempotency, specialty enablement rows,
and UX copy/routing updates. No correction of O1.1 is required beyond *not* adding the
previously proposed verified-gate.

## 2. Revised atomic provisioning model (APPROVED)

### 2.1 Endpoint contract (PROPOSED shape, to be frozen at build)

```
POST /api/v1/workspaces
Auth: get_current_user (any active user, verified OR unverified)
Tenant: none required (X-Tenant-less; sets its own scope server-side)
Headers: Idempotency-Key: <uuid v4, required>
Body: {
  clinic_name: str (1..200), slug: str (shape + reserved + unique),
  location_name: str (1..200, default "Main Clinic"),
  timezone: str (IANA, default "Asia/Kolkata"),
  practitioner_display_name?: str (default = user.display_name),
  specialty_codes: ["dental"] | ["ophthalmology"] | ["dental","ophthalmology"] (min 1),
  communication_config?: SKIPPABLE (absent in v1; future: deferred — never required)
}
Success: 201 {
  tenant{id,slug,status}, location{id}, membership{id},
  practitioner{id}, specialties_enabled[...],
  subscription{id,status:"trial",trial_ends_at,plan_code}
}
Errors: 400 validation / 401 unauth / 409 slug-taken or idempotency-payload-mismatch /
        422 unknown timezone or empty specialties (no-oracle not needed: slug availability
        is inherently observable to authenticated users; do NOT expose enumeration of
        other tenants' clinical data)
```

Hard rules: **no `user_id`/`owner` in body** (owner = `ctx.user_id` server-derived);
**no `email_verified` precondition**; **no payment/communication fields required**.

### 2.2 Transaction boundary (single DB transaction, all-or-nothing)

```
BEGIN
  1. authN (get_current_user) — verified status read for audit only, never gated
  2. idempotency lookup (user_id, key) -> replay-or-proceed (§2.3)
  3. validate slug (strip().lower(), ^[a-z0-9-]{3,63}$, reserved block:
     platform/api/admin/portal/login/signup/verify/health/metrics) -> 409 on taken
  4. validate timezone via ZoneInfo (is_valid_iana_timezone pattern) -> 422
  5. validate specialty_codes ⊆ registry keys, non-empty -> 422
  6. INSERT tenant (status active)
  7. SET app.tenant_id = new id (server-derived; same pattern as invites accept)
  8. INSERT location (name, validated timezone)
  9. INSERT membership (user, tenant, seed tenant_admin, is_primary=TRUE)
 10. INSERT tenant_owners (tenant, user, created_by=user) — ownership ≠ authorization
 11. INSERT practitioner stub (display_name, user link) + verification row (pending)
      Rationale: doctor profile step (journey step 4) persists even if the user skips
      the in-wizard form; approval stays a separate STAFF_MANAGE action.
 12. INSERT tenant_specialties rows (one per code + pack_version from registry)
      + location_specialties rows (inherit tenant set for the first location)
 13. INSERT subscriptions (trial plan, trial_ends_at = now + 14d, no card/gateway)
 14. audit append (workspace.provision, tenant.create, membership.create, refs only)
 15. outbox enqueue (welcome/getting-started notification, refs only; delivery
      post-P8.1C — stored not sent in O1)
 16. mark idempotency completed with result refs
COMMIT — any exception -> ROLLBACK all (zero tenant/location/membership/owner/
practitioner/specialty/subscription rows survive)
```

### 2.3 Idempotency (PROPOSED, replay-safe)

- Storage: small table `workspace_provisions(idempotency_key UUID, user_id FK,
  request_hash CHAR(64), status pending|completed|failed, tenant_id NULLABLE,
  result_refs JSONB refs-only, created_at, updated_at)` with
  `UNIQUE(user_id, idempotency_key)` (scope to the caller so keys never collide across
  users; Titan-style global-key table rejected — leaks cross-user existence).
- Behavior: same key + same `request_hash` (canonical JSON of body) → replay stored
  `201` (or in-flight `202` with `Retry-After` if still `pending`); same key + different
  hash → `409`; missing/malformed key → `422`. TTL 24h; background cleanup of stale
  `pending` rows. DB failover mid-commit is safe: replay finds `pending` without a tenant
  and re-executes; replay finds `completed` and returns refs.
- Alternative considered (stateless retry without a table): rejected — non-idempotent
  slug-taken side effects would orphan tenants on client timeout retries.

### 2.4 Validation details

- Slug: reuse `create_tenant` lowercasing + uniqueness (`ConflictError→409`), add shape +
  reserved validation in the workspace service (new code, not in `create_tenant`, to avoid
  changing the operator path's behavior).
- Timezone: `ZoneInfo(name)` must resolve (reuse `eligibility.is_valid_iana_timezone`);
  fix applies to the workspace path in O1.2 and, separately, to `clinics.create_location`
  validation (additive guard; existing stored values untouched).
- Specialty codes: membership test against `SPECIALTIES` registry keys; unknown → `422`.

### 2.5 Ownership vs authorization (APPROVED)

- `tenant_owners` is commercial authority ("who purchased/is responsible"), per
  `o1-security-and-data-model.md` §1 (adopted unchanged). Membership + `require(perm)` +
  `match_tenant` + RLS remain the ONLY access path. No endpoint checks `tenant_owners`
  as a substitute for permission.
- Invariants (service + tests): ownership never grants access; deactivating an owner never
  deletes data; last-owner protection mirrors last-admin (ordered `FOR UPDATE` guards);
  transfer = insert + audit, never client-supplied id writes; tenant scope always
  server-derived.
- O1 default: one owner (the provisioning caller). Schema supports N owners; multi-owner
  add/transfer endpoints are O2 unless explicitly approved.

### 2.6 Owner concurrency + last-owner protection (PROPOSED)

- Extend the `update_membership` ordered-lock pattern to owner writes: lock the tenant's
  owner rows (`SELECT ... ORDER BY user_id FOR UPDATE`) before demotion/removal, refuse to
  remove the final owner while `tenant.status = active`.
- Double-provision by the same user yields two independent tenants (multi-workspace
  primitive, already the test-helper semantic). Visiting-doctor second membership untouched.

## 3. Trial creation model (APPROVED commercial, PROPOSED schema)

- Every provisioned tenant gets exactly one `subscriptions` row in the same transaction:
  `plan = trial-14d` (seeded catalog row), `status = trial`,
  `trial_ends_at = now + 14 days`, no card, no charge, no gateway call, no auto-renew job.
- Trial = full operating capability (no enforcement interlocks in O1/O1.2). Negative tests
  MUST prove clinical/scheduling/billing/portal/invite/audit paths behave identically with
  and without (including expired-fixture) trial rows.
- Schema (new migration(s) after `0015`; exact numbering frozen at build, proposed
  `0016_tenant_ownership`, `0017_subscription_foundation`, `0018_specialty_enablement`):
  `subscription_plans` (non-RLS catalog: `code UNIQUE, name, trial_days DEFAULT 14,
  limits, is_active`), `subscriptions` (RLS `tenant_id = SETTING`, `tenant_id UNIQUE`,
  `plan_id RESTRICT`, `status CHECK(trial,active,past_due,grace,suspended,cancelled,expired)`,
  `trial_ends_at/period_start/period_end`), reuse `audit_events` (no new event table).
  Billing separation invariant holds: no subscription FK in clinic tables, no
  patient/clinical FK in subscription tables, `Money` pure functions shared only.
- Tenant read exposes `subscription{status, trial_ends_at, plan_code}` via existing
  `GET /tenants/{id}` (`TENANT_READ` + `match_tenant`); no other endpoint changes in O1.
- **O1.3 vs O1.2 split:** to honor "trial row created atomically with provisioning",
  the trial tables + seed plan SHOULD land in the same release train as provisioning
  (either inside O1.2's migration set or as an O1.3 migration merged before the
  provisioning route ships). Shipping provisioning without the trial insert is a
  release-blocker. Enforcement semantics remain O1.3/O2 (read-only visibility in O1).

## 4. Specialty enablement in provisioning (PROPOSED)

- `tenant_specialties` + `location_specialties` rows written in the provisioning txn
  (§2.2 steps 5/12). First location inherits the tenant set. Shell resolves effective
  specialties per request (§3 of specialty companion) and filters nav/forms/widgets/
  templates accordingly (hide-only).
- Dental-first default: if the user picks nothing, default `["dental"]` (explicitly
  recorded — no silent empty-means-legacy branch in new code).
- Existing (pre-pack) tenants: explicit `{dental}` backfill data note at migration time
  (recommended; avoids a legacy branch in resolution).

## 5. Revised onboarding journey (APPROVED flow, 6 steps + skippable comms)

Shortest practical path (authenticated steps 2–6 may resume after drop-off; progress
checklist persists on the tenant):

1. **Signup** — name + email + password → `202` → sign in. No inbox requirement.
   Copy: "Account created. Set up your clinic — verification is optional."
2. **Clinic details** — clinic name, slug (live availability, authenticated only),
   primary location name, timezone picker (IANA-validated, default Asia/Kolkata).
3. **Specialty selection** — cards for Dental / Ophthalmology (/ both). One-tap default
   (Dental preselected is acceptable if research confirms; else no preselect — UNRESOLVED,
   needs UX sign-off). Shows what each pack unlocks (forms, workflows, catalogues).
4. **Doctor profile** — display name (prefilled), optional registration no. / qualification
   (deferred fields — do NOT block). Creates/links practitioner stub + pending verification.
5. **Trial activation** — "Start 14-day full-access trial. No card. No automatic charge."
   Single button → atomic provision (§2). Shows trial end date on success.
6. **Workspace** — land in specialty-personalized shell (terminology, widgets, nav,
   shortcuts filtered; authorization unchanged). Progressive checklist: services, hours,
   staff invites, first patient, portal test — all skippable.

Explicitly NOT required: payment card, email verification, API credentials, staff
invitations, patient import, full clinic configuration. Communication configuration is a
skippable later step (Settings → Communications), never inline-blocking.

Mobile-first, one-thing-per-screen, 44px targets, `role=alert` error summaries with focus,
WCAG 2.2 AA, existing `packages/ui` tokens/components only (DESIGN.md §12). New statuses
(trial, pack-enabled) extend `status.ts` mappings — never client-invented strings.

## 6. Frontend / API surface (PROPOSED)

- New: `app/(public)/signup` (copy update: optional-verification), `app/workspaces/new`
  (6-step wizard), shell specialty filter (`lib/specialties.ts` reading
  `specialty_capabilities`), `app/platform/tenants` read-only (O1.4).
- Edit: `login` (route unverified users to workspace setup, not to a lock screen),
  `verify` (reword as optional assurance), `NAV` → specialty-filtered (hide-only),
  `encounters/[id]` dental tab → pack-gated render.
- New API: `POST /workspaces` (§2.1), `GET /specialties/capabilities` (tenant-scoped read
  for the shell; `TENANT_READ`-gated). Edit: `GET /tenants/{id}` (+ subscription +
  specialties). No mutation of platform status in O1.

## 7. Exact implementation sequence (APPROVED order; each a separate slice)

1. **O1.0R (this slice, docs only):** merge these four docs + amendment headers on
   superseded docs. Gate: git shows only `docs/commercial/*` changed; no migration/code.
2. **O1.2a — provisioning + trial + specialties foundation (one release train):**
   migrations (`tenant_owners`, `subscription_plans`+`subscriptions`+seed `trial-14d`,
   `tenant_specialties`+`location_specialties`, `workspace_provisions`), IANA validator,
   `POST /workspaces` (+ idempotency, ownership, trial insert, specialty rows, audit/outbox),
   `GET /tenants/{id}` extension. Tests: atomicity (fault injection → zero rows),
   idempotency matrix, slug/timezone/specialty validation, double-provision independence,
   unverified-provision **allowed** (replaces old unverified-403 test), unauth 401,
   trial-row-exists + negative-enforcement tests, RLS tests for new tables.
3. **O1.1R — verification-optional hardening (no schema):** copy/routing updates so no
   screen implies verification is required; keep verify/resend behavior; add
   email-change gap to backlog with the §2.6 contract as the acceptance note.
   Tests: existing `test_signup_api.py` suite stays green (it already passes with optional
   verification — the only gate test, `test_require_verified_email_gate`, is updated to
   assert the helper exists but is NOT called by provisioning).
4. **O1.3R — trial visibility (read-only):** platform + tenant subscription/specialty
   reads; seed-plan uniqueness test; billing-separation schema test. No enforcement gates.
5. **O1.4R — read-only platform console:** list/search/detail (+ owners refs +
   subscription + specialties), pagination, audit, 403 for non-admins. No mutations.
6. **O1.5R — E2E + isolation:** synthetic two-pilot provision via signup→workspaces
   (Nevase dental + independent eye clinic), full isolation matrix (extends
   `test_p8_two_tenant_pilots.py`), cross-tenant subscription/specialty probes 403/404,
   release gates (`ruff+mypy+pytest`, single head, migrate review, preview smoke).
7. **O2+ (deferred):** specialty pack modules (ophthalmology build after discovery sign-off),
   email-change endpoint, comms providers (platform email, BYO, WATI/BSP), subscription
   enforcement/checkout/dunning, metering, branding/white-label, imports, support access.

O1.1 MUST NOT be deleted. `0015` MUST NOT be reverted. `require_verified_email` MUST NOT
be wired into provisioning.

## 8. Decisions ledger

- APPROVED: frictionless (no mandatory verification); 14-day no-card full-capability trial
  atomically provisioned; comms skippable; one generic OS; registry-based packs (no
  marketplace/dynamic loading); WhatsApp-Web-vs-API distinction; ownership≠authorization.
- PROPOSED (recommended, needs build-time freeze): §2.1–2.4 contracts, specialty both-level
  model, registry shape, comms adapter details, email-change contract, legacy `{dental}`
  backfill over empty-means-legacy.
- UNRESOLVED (needs owner sign-off before/at build): grace/trial-expiry/subscription-expiry
  behavior; retention + export; plan limits + proration + period boundaries; refund policy;
  visiting-doctor billing identity; platform support access + countersign; multi-owner
  first-release scope; specialty default/preselect; location-vs-tenant scoping in v1;
  `practitioner_specialties` necessity; legacy-default mechanism; BYO provider list +
  sender-identity ownership; receipt retention; WATI-vs-BSP priority.
- DEFERRED (explicitly not in O1): enforcement gates, payment gateway/webhooks/receipting,
  provider implementations, metering tables, working-hours/branding/imports, portal SKU,
  support-access grants, Docker/CI changes, prod data access.

## 9. Files created/updated (this slice)

- Created: `docs/commercial/frictionless-onboarding.md`,
  `docs/commercial/specialty-pack-architecture.md`,
  `docs/commercial/communications-architecture.md`,
  `docs/commercial/o1-revised-implementation-plan.md` (this file).
- Updated (amendment headers only, no requirement deletion):
  `docs/commercial/o1-implementation-plan.md`, `docs/commercial/o1-security-and-data-model.md`,
  `docs/commercial/o1-acceptance-criteria.md`, `docs/commercial/onboarding-journey.md`
  (exact headers applied alongside this plan where the tool permits; if any header failed
  to apply, treat this §9 + §1 precedence note as governing).

## 10. Rollback

Docs-only: revert the four files (and any applied amendment headers). No runtime effect;
no migration to downgrade; no code path depends on these docs.

## 11. Multi-platform alignment (2026-11-08 — APPROVED, docs only)

No contract change in this amendment. Provisioning (§2), trial (§3), specialty
enablement (§4), and journey (§5) apply identically to every surface in
`docs/product/application-surfaces.md`: one backend, one `POST /workspaces`, one trial
model, registry packs configuring (never authorizing) web/EXE/APK/PWA shells.

- O1.1.1 (new, before O1.2a): frictionless identity alignment — verification-optional
  copy/routing, no schema, existing `test_signup_api.py` green.
- O1.2a/O1.3R/O1.4R/O1.5R: unchanged in substance; §7 sequence now reads
  O1.1.1 → O1.2 → O1.3 → O1.4 → O1.5, then A1 → A2/A3 → A4/A5 → A6, with S1 riding O1.2
  enablement and C1/W1 after O1.5. Full structure: `docs/roadmap/healthcare-os-product-roadmap.md`.
- Native shells (Tauri EXE / Capacitor APK candidates) consume the same contracts over
  cookie-or-Bearer auth (`cookies.py` fallback already exists); no native-only auth or
  clinical route. No Tauri/Capacitor dependency in this slice.
- Decision states: multi-platform structure + roadmap + client trust model = APPROVED;
  Tauri-vs-alternatives / Capacitor-vs-alternatives / updater / pinning / push = PROPOSED
  pending spike; offline desktop, local clinical DB, iOS = DEFERRED (explicit).
