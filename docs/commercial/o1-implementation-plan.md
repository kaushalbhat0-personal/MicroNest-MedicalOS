# AMENDMENT (2026-11-08, frictionless onboarding — GOVERNING)

> The verification-gated provisioning contract below (§§6–9, `POST /workspaces`
> requiring verified email) is SUPERSEDED by
> `docs/commercial/o1-revised-implementation-plan.md` + `frictionless-onboarding.md`.
> Provisioning MUST NOT require verification. O1.1 verification remains as an optional
> capability; `0015` is retained. Trial row creation is atomic with provisioning.
> This file is preserved for history; the revised plan governs on conflict.

# O1 Implementation Plan (Decision Lock + Preflight)

Status: planning ONLY. No schema, API, or behavior changes in this slice.
Companions: `o1-security-and-data-model.md`, `o1-acceptance-criteria.md`.
Sources: `docs/commercial/customer-onboarding-architecture.md`,
`docs/commercial/subscription-domain-discovery.md`,
`docs/commercial/onboarding-journey.md`.

## 0. Git baseline (recorded before work)

- Branch: `main`
- HEAD: `efefb0a3b31ff3c32a090506961d6f875a51b612`
- Modified (pre-existing, preserved, not touched):
  `M .env.example`, `M .github/workflows/ci.yml`,
  `M apps/web/app/encounters/page.tsx`, `M apps/web/app/globals.css`,
  `M apps/web/app/layout.tsx`, `M apps/web/app/login/page.tsx`,
  `M apps/web/app/page.tsx`, `M apps/web/app/schedule/page.tsx`,
  `M apps/web/app/sessions/page.tsx`, `M apps/web/app/team/page.tsx`,
  `M apps/web/package.json`, `M backend/app/api/v1/router.py`,
  `M backend/app/api/v1/tenants.py`, `M backend/app/main.py`,
  `M backend/app/platform/authz/permissions.py`, `M backend/app/platform/config.py`,
  `M backend/app/platform/events/worker.py`, `M backend/app/platform/ops.py`,
  `M backend/app/platform/ports/ports.py`, `M backend/app/requirements.txt`,
  `M package-lock.json`, `M packages/ui/Button.tsx`, `M packages/ui/index.ts`,
  `M packages/ui/package.json`, `M packages/ui/tokens.css`,
  `M tests/conftest.py`, `M tests/unit/test_permissions.py`
- Untracked (pre-existing, preserved): `.dockerignore`,
  `.playwright-mcp/*`, `DESIGN.md`, `apps/web/AGENTS.md`,
  `apps/web/Dockerfile`, `apps/web/app/admin/page.tsx`,
  `apps/web/app/billing/**`, `apps/web/app/dental/**`,
  `apps/web/app/encounters/[id]/page.tsx`, `apps/web/app/icon.svg`,
  `apps/web/app/patients/**`, `apps/web/app/portal/**`,
  `apps/web/app/reception/page.tsx`, `apps/web/app/shell.tsx`,
  `apps/web/lib/{nav,portal,use-api}.ts`, `apps/web/postcss.config.mjs`,
  `backend/alembic/versions/0013_portal.py`,
  `backend/alembic/versions/0014_portal_selfread.py`,
  `backend/app/api/v1/portal.py`, `backend/app/modules/notifications/eligibility.py`,
  `backend/app/modules/portal/**`, `backend/app/platform/adapters/*`,
  `docs/architecture/deployment.md`, `docs/commercial/*` (3 discovery docs),
  `docs/database/p7-operations.md`, `docs/decisions/*`, `docs/pilots/*`,
  `docs/specialties/*`, `infrastructure/preview/*`, `packages/ui/*` (new components),
  `scripts/*`, `tests/deployment/*`, `tests/isolation/*`, `tests/portal/*`,
  `tests/unit/test_*p7*`, `test_design_tokens`, `test_notification_eligibility`
- Rule for O1: do not reset, clean, stash, discard, commit, or push.
  Only these three planning files may be created/updated.

## 1. What exists (verified with code refs)

- Identity: `backend/app/modules/identity/service.py:59-78` `create_user`
  (ConflictError on duplicate); `backend/app/api/v1/auth.py:25-63` login
  (per-IP + per-account throttle, no-oracle 401);
  `backend/app/api/v1/account.py:109-166` reset request/confirm
  (202 no-oracle, 2h single-use token `identity/service.py:237-268`).
  No signup route: `backend/app/api/v1/router.py:22-35` mounts
  auth/account/invites/platform/tenants/audit/patients/scheduling/
  encounters/prescriptions/dental/billing/portal only.
- Tenancy: `tenancy/service.py:40-55` `create_tenant` (slug unique,
  status active); `clinics/service.py:23-41` `create_location`
  (name-unique-per-tenant, timezone unvalidated default `Asia/Kolkata`);
  `tenancy/service.py:115-146` `create_membership` (one user+tenant row,
  ConflictError on dup); `tenancy/service.py:327-382` `update_membership`
  (ordered `FOR UPDATE OF Membership` last-admin guard).
  Location scope relational (`MembershipLocation`), empty = all locations
  (`platform/authz/scope.py:10-33`).
- Tenant selection: `api/deps.py:116-167` `get_ctx` (X-Tenant selector only,
  single-membership default, 403 fail-closed, blocks `status != active` at
  `:145`, sets `app.tenant_id`/`app.user_id`/`app.actor_id`);
  `api/v1/_shared.py:30-34` `match_tenant` (mismatch = 404 anti-oracle).
- Invites: `tenancy/service.py:172-250` create (`token_urlsafe(48)`,
  sha256 stored, 7d TTL) / accept (tenant-active check, existing-user adopt,
  single-use); `api/v1/invites.py:23-57` public accept (IP-throttled,
  server-derived tenant, issues session pair).
- Portal: `portal/service.py:49-113` staff-gated enroll, one
  `(tenant,user)` -> patient, unusable random password;
  `portal/models.py:18-31` `portal_links` unique `(tenant,user)`.
- Platform admin: `api/deps.py:170-180` `get_platform_admin`
  (`is_platform_admin` flag check, tenant-free);
  `api/v1/platform.py:21-49` only `GET /health` + `POST /tenants`.
  `set_tenant_status` (`tenancy/service.py:65-68`) exists, zero callers.
  Web `/admin` (`apps/web/app/admin/page.tsx`) is tenant admin
  (locations/roles/audit), not a platform console.
- Billing: `modules/billing/` isolated Decimal-only `money.py:18-79`
  (INR-only, float rejected); no plan/seat/subscription references.
- RLS: `alembic/versions/0005_rls.py:23-85` (hos_app, FORCE RLS,
  `*_tenant_isolation` policies; `memberships` self-read exception;
  `roles` seed-readable; `invitations`/`users`/`sessions`/`tenants` non-RLS,
  service-gated). Migrations linear `0001_identity` -> `0014_portal_selfread`;
  app never migrates at startup (`app/main.py:1-6`,
  `scripts/db-migrate.sh` owner-URL + backup gate).
- Frontend: one public route `/login` (`apps/web/app/login/page.tsx`);
  `lib/tenant.ts` stores only tenant selector in localStorage;
  `lib/api.ts` cookie sessions; no signup/pricing/onboarding routes.
- Tests: real Postgres + `alembic upgrade head` + TRUNCATE
  (`tests/conftest.py:38-174`); isolation pattern
  `tests/isolation/test_p8_two_tenant_pilots.py:1-318`.

## 2. Conflicts between proposal and implementation (must resolve in O1.0)

1. `owner_user_id` on tenant is insufficient (single FK cannot hold N
   owners; nullability/transfer semantics unclear). Resolved by explicit
   `tenant_owners` join (see §4).
2. `is_primary` is a UX hint, not authority
   (`tenancy/models.py:65`, `ops.py:100-102`). Must never be treated as
   ownership proof.
3. Timezone unvalidated (`clinics/service.py:24`). O1.2 must add IANA
   validation at write (reuse `ZoneInfo` pattern from
   `notifications/eligibility.py:149-169`).
4. `set_tenant_status` blind setter, no validation, no endpoint
   (`tenancy/service.py:65-68`, `platform.py`). O1 must not expose status
   mutation; O1.4 is read-only.
5. Discovery suggests "block new enrollments when suspended" — no
   enforcement point may block reads. O1 implements no suspension
   enforcement at all (foundation rows + read views only).
6. Discovery mentions trial limits (seats/locations/SMS). No metering
   exists. O1 stores plan + subscription rows only; enforcement is O2.

## 3. O1 scope (what is IN)

- O1.0 Architecture and decision lock (this plan + companions).
- O1.1 Identity signup + email verification (new public endpoints,
  token lifecycle, throttles, no-oracle).
- O1.2 Atomic clinic provisioning (one transaction:
  tenant + location + owner membership + owner practitioner stub (optional)
  + trial subscription + ownership row + audit; idempotent; rollback-all).
- O1.3 Trial subscription foundation (tables + seed plan + status read;
  no charges, no gateway, no enforcement gates on clinical reads/writes).
- O1.4 Read-only platform administration (tenant list/search/detail +
  subscription visibility; no mutations; support access stays deferred).
- O1.5 End-to-end onboarding + isolation verification (synthetic two-pilot
  provision via future API, cross-tenant probes, release gates).

## 4. Explicit exclusions (NON-NEGOTIABLE)

No payment provider / gateway / webhook / receipting (O4). No notification
provider (P8.1B eligibility preserved, P8.1C delivery stays deferred; O1
reuses existing notify request path with dev-console/none only).
No subscription enforcement gates on clinical/portal/audit reads or writes
in O1 (foundation rows only). No patient-portal SKU. No subscription keys
in clinic billing tables and no patient/clinical keys in subscription
tables. No client-supplied `user_id`/`owner` trust. No service-role
credentials in browser. No RLS weakening. No SQLite/dialect fork. No
destructive migrations. No Docker/CI architecture changes. No production or
preview DB writes. No multi-owner release in O1.1-O1.2 unless D-decision
(see §9) explicitly approves; single-owner default with multi-owner-ready
schema.

## 5. Proposed database relationship model (details in companion)

New tables (all UUIDv7 PK, `created_at/updated_at timestamptz`):

- `email_verifications(id, email CITEXT-or-lowercased text unique-per-pending,
  token_hash text unique, expires_at, used_at, attempts, created_at)`.
  Non-RLS, capability-gated like `invitations`.
- `tenant_owners(id, tenant_id FK CASCADE, user_id FK CASCADE,
  created_at, created_by FK SET NULL, uq(tenant_id, user_id))`.
  RLS `tenant_id = SETTING` (same pattern as `memberships`).
  Authority for "who owns this clinic". Membership still required for access.
- `subscription_plans(id, code unique, name, max_locations int,
  max_practitioners int, max_staff_seats int, trial_days int,
  is_active, created_at)`. Non-RLS catalog (like seed roles), seeded by
  migration, never edited in place (new row versioning).
- `subscriptions(id, tenant_id FK CASCADE unique, plan_id FK RESTRICT,
  status text, trial_ends_at, period_start, period_end,
  created_at, updated_at, uq(tenant_id))`.
  RLS `tenant_id = SETTING`. Statuses in O1: `trial` (+ `active` reserved;
  `past_due/grace/suspended/cancelled/expired` defined but unwired until O2).
- Optional `subscription_events` OR reuse `audit_events` with refs only.
  Default: reuse `audit_events` (no new table in O1).

Unchanged: `tenants` (no `owner_user_id` column),
`memberships`/`roles`/`locations`/`portal_links`/all billing tables.
Tenant `status` stays `active` through O1 (suspension unwired).

## 6. Migration ordering

Strictly linear after `0014_portal_selfread`:

- `0015_signup_verification` — `email_verifications` table + indexes
  (`token_hash` unique, partial unique on pending `(email)`), grants.
- `0016_tenant_ownership` — `tenant_owners` table + RLS policy
  `tenant_owners_tenant_isolation` + grants. No backfill (zero self-service
  tenants exist; bootstrap tenants get ownership rows via data note only
  if product approves — default: no backfill in O1).
- `0017_subscription_foundation` — `subscription_plans` +
  `subscriptions` + RLS on `subscriptions` + seed `trial` plan row
  (code `trial-14d`, 14-day proposed default, limits TBD per D6).

Each migration: `revision = <stem>`, `down_revision = <prev stem>`,
`upgrade` creates tables/policies/grants, `downgrade` drops policy +
tables (no data destruction concern: O1 tables empty in prod).
`ops.py:APP_TABLES` extended with the three new app tables.
No migration edits `tenants`, billing, or portal tables.

## 7. API contracts (lifecycle)

O1.1 (public, no auth; per-IP throttles; no-oracle where noted):

- `POST /api/v1/auth/signup {email, password, display_name}`
  -> `202 {"status":"accepted"}` always (no existence oracle).
  Creates `User` (no credential? or inactive + credential pending verify —
  decision locked in O1.0: create user with credential but `is_active=True`
  and `email_verified=False`? See companion §6 — recommended: separate
  `email_verified` flag OR verification-gated login; exact column decided
  in O1.0, implemented in O1.1) + `email_verifications` row + notify request
  (`verify_email` template, refs only). Duplicate email: no new row, same
  202, resend-verify path instead of error (no oracle).
- `POST /api/v1/auth/verify {token}` -> `200 {"status":"ok"}` /
  `410 GoneError("verification invalid or expired")` (indistinguishable
  bad/used/expired/throttled). Single-use (`used_at`), 24h TTL (proposed),
  sha256 stored, raw never persisted.
- `POST /api/v1/auth/verify/resend {email}` -> `202 accepted` always.
  Throttled per-IP + per-email (reuse `reset:ip` limits as baseline).

O1.2 (authenticated, no X-Tenant required; Idempotency-Key required):

- `POST /api/v1/workspaces {clinic_name, slug, location_name, timezone,
  practitioner_display_name?} + Idempotency-Key: <uuid/v4>`
  -> `201 {tenant{id,slug,status}, location{id}, membership{id},
  subscription{id,status,trial_ends_at}}` /
  `409 ConflictError` (slug taken) / `422` (bad timezone/slug shape).
  Preconditions: caller authenticated, email verified (else 403).
  Transaction boundary: single DB txn — tenant, location (IANA-validated),
  owner membership (`tenant_admin` seed role), `tenant_owners` row
  (caller user id server-derived), trial `subscriptions` row (seed plan),
  optional practitioner stub + pending verification, audit `workspace.provision`
  (refs only). Any failure rolls back all. Idempotency: key stored
  (new `provision_idempotency` table or reuse outbox pattern — locked in
  O1.0; recommended small table `workspace_provisions(idempotency_key unique,
  user_id, tenant_id NULLABLE, status, created_at)`) with 24h window;
  same key + same payload returns prior result, same key + different
  payload -> 409.

O1.3 (no new public endpoints): subscription rows readable via
`GET /api/v1/tenants/{id}` extension (`subscription{status, trial_ends_at,
plan_code}`) gated by existing `TENANT_READ` + `match_tenant`.
No enforcement interlocks in O1.

O1.4 (platform admin only, read-only):

- `GET /platform/tenants?q=&status=&limit=&cursor=` (paginated, slug/name
  search, no clinical fields).
- `GET /platform/tenants/{id}` (tenant + owners (user refs) + subscription
  + membership count; no patient/clinical rows).
- `GET /platform/subscriptions?status=&limit=&cursor=` (optional; may fold
  into tenant detail if product prefers fewer endpoints — locked O1.0).
- No `PATCH/POST /platform/tenants/{id}/status` in O1. No support-access
  grant flow in O1 (`SUPPORT_GRANT` stays defined-only).

## 8. Provisioning transaction boundary

```
BEGIN
  1. authN (get_current_user) + verified-email check (service, not client flag)
  2. idempotency lookup (key, user) -> replay or proceed
  3. validate slug shape + uniqueness (ConflictError, no oracle concern:
     slugs are public identifiers; availability endpoint optional O1.5)
  4. validate timezone via ZoneInfo (ValidationError on unknown)
  5. INSERT tenant (status active)
  6. SET app.tenant_id = new id (service-verified, never client input)
  7. INSERT location
  8. INSERT membership (tenant_admin, is_primary=True UX hint)
  9. INSERT tenant_owners (tenant, user)
  10. INSERT subscriptions (trial plan, trial_ends_at = now + 14d proposed)
  11. OPTIONAL practitioner stub + pending verification
  12. audit append (workspace.provision, tenant.create, membership.create refs)
  13. outbox enqueue (welcome notification post-P8.1C; stored, not sent in O1)
COMMIT (or ROLLBACK all on any error)
```

Failure/retry: client retries with same Idempotency-Key on timeout/5xx;
different payload with same key -> 409 (must generate new key).
DB failover mid-commit: idempotency row (written first, `status=pending`)
allows safe replay; orphan tenants impossible outside txn.

## 9. Product decisions (proposed defaults, NOT approved)

- D1: owner may invite staff during trial. Proposed default: yes (trial =
  full operating capability). Gate at accept (not invite-create) so
  outstanding invites survive brief states. Needs approval.
- D5: suspension never destroys data, never blocks clinical/portal/audit/export
  reads. Proposed: always. Needs approval (listed as approved in brief's
  D5 line but treated as proposed here pending explicit sign-off).
- D9: 14-day trial, no card, no automatic charge. Proposed default.
  Needs approval.
- Unresolved (do NOT silently decide; each needs owner sign-off):
  grace duration/behavior; trial-expiry behavior; subscription-expiry
  behavior; retention + export policy/format/availability; plan limits +
  proration + period boundaries; refund policy; visiting-doctor billing
  identity; platform support access + countersign; whether multiple owners
  allowed in first release (schema supports N owners; O1 behavior default:
  single owner per provision, transfer/add deferred to O2 unless approved).

## 10. O1 phase plan with measurable gates

- O1.0 Architecture + decision lock. Exit: this plan + 2 companions merged
  as docs-only; all §9 items explicitly marked proposed vs approved;
  migration/API/table names frozen.
- O1.1 Signup + verification. Exit: public signup/verify/resend live,
  no-oracle + throttle tests green, token single-use/expiry tests green,
  no login bypass (unverified cannot provision), RLS intact.
- O1.2 Atomic provisioning. Exit: single-txn provision + idempotency +
  IANA validation + rollback tests green; duplicate slug 409; second
  provision by same user creates independent tenant (multi-ownership primitive).
- O1.3 Trial foundation. Exit: `0017` applied, seed plan present, every
  provisioned tenant has exactly one `trial` subscription, tenant read
  exposes trial status, zero enforcement on clinical paths (negative tests).
- O1.4 Read-only platform console. Exit: list/search/detail endpoints
  behind `get_platform_admin`, no mutation routes, no clinical payloads,
  pagination + audit coverage.
- O1.5 E2E + isolation. Exit: synthetic two-pilot provision via new API,
  full isolation matrix green (extension of `test_p8_two_tenant_pilots.py`),
  cross-tenant subscription probes 403/404, release gates in §12 green.

## 11. Exact expected implementation files (O1.1-O1.5, NOT this slice)

Backend new: `app/modules/signup/{models,service,schemas}.py` (or
`modules/identity/verification.py` — lock in O1.0),
`app/api/v1/signup.py`, `app/api/v1/workspaces.py`,
`app/modules/subscriptions/{models,service}.py`,
`app/api/v1/platform_tenants.py` (read views; or extend `platform.py`).
Backend edit: `api/v1/router.py` (mount), `api/v1/tenants.py`
(subscription read extension), `platform.py` (read views only),
`modules/identity/service.py` (verified-email flag helpers),
`modules/clinics/service.py` (IANA validation),
`platform/ops.py` (APP_TABLES + optional backfill note),
`platform/config.py` (new throttle limits), `alembic/versions/0015_*`,
`0016_*`, `0017_*`.
Frontend new: `app/(public)/signup/page.tsx`, `app/(public)/verify/page.tsx`,
`app/workspaces/new/page.tsx`, `app/platform/tenants/page.tsx`
(naming follows existing `app/` convention; no middleware — client guards
like `login/page.tsx`).
Tests new: `tests/service/test_signup.py`, `tests/api/test_signup_api.py`,
`tests/service/test_provisioning.py`, `tests/api/test_workspaces_api.py`,
`tests/service/test_subscriptions.py`, `tests/api/test_platform_readonly.py`,
`tests/isolation/test_o1_two_pilot_provisioning.py`.
No changes to: `tenants` table migration, billing tables, portal tables,
RLS policies on existing tables, Dockerfiles, compose, CI architecture.

## 12. Test and release gates

Unit: password/verification token hashing (sha256 stored, raw never),
trial-period math, slug normalize, timezone accept/reject matrix.
Service: signup duplicate no-oracle, verify single-use/expiry,
provision atomicity (fault injection -> zero rows), idempotent replay
(same key same result; same key diff payload 409), multi-owner-ready
(second provision independent), last-owner guard analogue.
API: throttle 429/401 shapes, `match_tenant` 404 anti-oracle preserved,
unverified-provision 403, platform endpoints 403 for non-admins,
tenant list contains zero clinical fields.
Isolation: extend `test_p8_two_tenant_pilots.py` pattern — A/B tenants via
new provision path; cross reads 404; B subscription state never affects A;
revoked/second-user probes.
Release: `ruff + mypy + pytest` green; single alembic head;
`scripts/db-migrate.sh` review gate; preview smoke; docs-only O1.0 merges
without migration.

## 13. Rollback strategy

O1.0: revert docs commit (no runtime effect). O1.1-O1.3: migrations are
additive; downgrade drops new tables/policies (empty in early rollout);
code rollback safe because no existing endpoint depends on new tables
(provision path is new route; login/reset/invite untouched). O1.4: read-only
routes removable without data effect. No destructive migration ever;
no backfill to undo (default no backfill).
