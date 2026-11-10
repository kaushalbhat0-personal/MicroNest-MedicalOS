# AMENDMENT (2026-11-08, frictionless onboarding — GOVERNING)

> O1.1/O1.2 gates below that require verified email before `POST /workspaces`
> (incl. "unverified 403" tests) are SUPERSEDED by
> `docs/commercial/o1-revised-implementation-plan.md`: unverified provisioning MUST
> succeed; verification stays optional. This file is preserved for history.

# O1 Acceptance Criteria

Status: planning ONLY. Each phase below is a separate implementation slice.
Do not combine phases into one change. No code in this slice.

Notation: MUST = release-blocking; SHOULD = expected unless waived with reason.

## O1.0 — Architecture and decision lock (this slice)

- [ ] MUST: this plan + `o1-security-and-data-model.md` + this file exist
  under `docs/commercial/` and reference all three discovery docs.
- [ ] MUST: every §9 product decision in the plan is labeled proposed vs
  approved; zero silent decisions. Unresolved list contains at minimum:
  grace terms, trial-expiry, subscription-expiry, retention + export,
  plan limits + proration, refund policy, visiting-doctor billing identity,
  support access + countersign, multi-owner first-release scope.
- [ ] MUST: ownership model locked as explicit `tenant_owners` join;
  `owner_user_id` rejected with reasons recorded.
- [ ] MUST: migration names (`0015/0016/0017`), table names, endpoint paths,
  and Idempotency-Key contract frozen.
- [ ] MUST: git baseline recorded (§0 of plan); post-work `git status`
  shows initial modified/untracked files intact plus only these three new
  docs. No tracked implementation file modified; no migration created;
  no commit/push.

## O1.1 — Identity signup and email verification

Functional:

- [ ] MUST: `POST /auth/signup` returns `202 accepted` for new, duplicate,
  and throttled cases (no oracle). New email creates user + pending
  verification row + notify request (refs only).
- [ ] MUST: `POST /auth/verify` accepts a valid token once (`200 ok`,
  marks verified); second use / expired / malformed / throttled all return
  identical `410` (no oracle).
- [ ] MUST: `POST /auth/verify/resend` returns `202` always; per-email
  throttle enforced (proposed 3/hour).
- [ ] MUST: unverified users can log in but `POST /workspaces` returns 403.
- [ ] MUST: passwords keep Argon2id + min-12 (`passwords.py` unchanged);
  tokens `token_urlsafe(48)` + sha256 at rest (invite/reset pattern).

Security / isolation:

- [ ] MUST: rate-limit tests (IP + account + resend) green.
- [ ] MUST: no `service-role` / `APP_ROLE_PASSWORD` / `OWNER_DATABASE_URL`
  in any `apps/web` file (existing hygiene gate extended).
- [ ] MUST: RLS on existing tables unchanged (single-head migration check).

Tests (new `tests/service/test_signup.py`, `tests/api/test_signup_api.py`):

- signup new -> 202 + row pending; duplicate -> 202 + zero new users;
  verify ok -> verified; replay -> 410; expired -> 410; resend throttle.
  All DB-backed via `conftest.py` harness (real Postgres + RLS role).

## O1.2 — Atomic clinic provisioning

Functional:

- [ ] MUST: `POST /workspaces` (auth, verified, Idempotency-Key required,
  no X-Tenant) returns 201 with tenant + location + membership +
  subscription(trial) refs on success.
- [ ] MUST: single transaction — fault injection (e.g. duplicate slug
  mid-path, bad timezone, plan missing) leaves zero tenant/location/
  membership/owner/subscription rows.
- [ ] MUST: same key + same payload -> identical 201 replay; same key +
  different payload -> 409; missing key -> 422/400.
- [ ] MUST: slug validation (shape, reserved list, 409 on taken);
  timezone IANA validation (422 on unknown; `Asia/Kolkata` default kept).
- [ ] MUST: owner = caller id only; caller-chosen role ignored (always
  seed `tenant_admin`); location validated in-tenant.
- [ ] MUST: same user provisioning twice yields two independent tenants
  (multi-workspace primitive); visiting-doctor second-membership flow
  untouched.

Tests (new `tests/service/test_provisioning.py`,
`tests/api/test_workspaces_api.py`): atomicity, idempotency matrix,
validation matrix, double-provision independence, unverified 403,
unauthenticated 401.

## O1.3 — Trial subscription foundation

- [ ] MUST: migrations `0015/0016/0017` apply cleanly in order; single head;
  `downgrade` drops new tables/policies only.
- [ ] MUST: seed plan `trial-14d` present exactly once; every O1 provision
  creates exactly one `subscriptions(status=trial)` row linked to it.
- [ ] MUST: tenant read exposes `subscription{status, trial_ends_at,
  plan_code}` to members with `TENANT_READ`; no other endpoint changes.
- [ ] MUST (negative): zero enforcement interlocks — clinical scheduling,
  encounters, billing, portal reads/writes, invites accept, and audit reads
  behave identically with and without trial rows (expired-trial fixture
  changes nothing in O1).
- [ ] MUST: billing separation — no subscription FK in billing tables, no
  patient/clinical FK in subscription tables (schema test).

## O1.4 — Read-only platform administration

- [ ] MUST: `GET /platform/tenants` (search `q`, paginated, capped limit)
  + `GET /platform/tenants/{id}` (+ owners refs + subscription) behind
  `get_platform_admin`; non-admin -> 403; unauth -> 401.
- [ ] MUST: responses contain zero patient/clinical/billing rows and zero
  contact contents (refs only).
- [ ] MUST: no mutation route added (`POST/PATCH/DELETE` on platform
  tenants/subscriptions absent; `set_tenant_status` still unwired).
- [ ] MUST: every platform read appends audit (refs only).
- [ ] MUST: web console (if any in O1.4) is read-only; no status buttons.

## O1.5 — End-to-end onboarding and isolation verification

- [ ] MUST: synthetic two-pilot script (Nevase dental + independent eye
  clinic, per `onboarding-journey.md` §3) provisions both tenants solely
  via `signup -> verify -> workspaces` with synthetic data only.
- [ ] MUST: isolation matrix green (extension of
  `test_p8_two_tenant_pilots.py`): tenants/locations/memberships/patients/
  appointments/clinical/invoices/portal-links/audit independent;
  cross-tenant reads 404; `X-Tenant` required for dual members;
  B subscription state never affects A.
- [ ] MUST: cross-tenant subscription probes (tenant A id with B session,
  forged subscription id/UUID) return 403/404 with zero data.
- [ ] MUST: full gates green: `ruff check`, `ruff format --check`,
  `mypy backend/app`, `pytest`, single alembic head, `db-migrate.sh`
  review passes, preview compose + smoke pass, Docker images build
  (no Dockerfile/compose/CI architecture changes).
- [ ] MUST: docs updated with trial terms as proposed-defaults and the
  unresolved-decision list carried forward to O2.

## Global release gates (every O1.1-O1.5 slice)

1. `pytest -q` green on real Postgres; new tests use `owner_db`/`client`
   fixtures (never SQLite, never prod/preview DB).
2. `ruff`, `mypy`, `npm run typecheck` + `next build` (web) green.
3. `alembic history -r current:head` shows exactly one head; migrate review
   gate passes.
4. No `localStorage/sessionStorage(token|refresh|secret|password)` in web;
   no secret committed (hygiene gate).
5. Rollback note in slice PR: which migration(s) drop what; code removal
   leaves existing auth/tenant/billing behavior intact.

## Explicit non-goals (acceptance MUST confirm absence)

No gateway credentials/endpoints, no charge/dunning/proration logic, no
`platform.tenant.suspend` endpoint, no suspension enforcement, no portal
SKU, no specialty/working-hours/branding/import features, no support-access
grant, no Docker/CI changes, no prod data access.
