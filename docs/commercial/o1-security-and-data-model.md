# AMENDMENT (2026-11-08, frictionless onboarding — GOVERNING)

> `POST /auth/verify`-gated provisioning (§§3–4) is SUPERSEDED by
> `docs/commercial/o1-revised-implementation-plan.md` + `frictionless-onboarding.md`:
> login/provisioning work unverified; `require_verified_email` is NOT a provisioning
> precondition (retained for future progressive assurance only). This file is preserved
> for history; the revised plan governs on conflict.

# O1 Security and Data Model

Status: planning ONLY. Companion to `o1-implementation-plan.md`.
No code, migration, or data change in this slice.

## 1. Ownership model recommendation (locked proposal)

Use an explicit ownership relationship. Do NOT use `owner_user_id`.

Why `owner_user_id` fails:

- One doctor may own N clinics: a single FK on `users` or `tenants` forces
  either N nullable columns or a second table anyway.
- A clinic may have N owners: a scalar column cannot represent the set,
  and "primary owner + others" reintroduces the `is_primary` ambiguity.
- Transfer/audit needs history: a column overwrite loses who granted what
  when; a row insert + audit append preserves it.

Recommended (O1):

```text
users 1---N tenant_owners N---1 tenants
users 1---N memberships  N---1 tenants
```

- `tenant_owners`: the commercial authority ("who purchased / is
  responsible for this clinic"). Columns:
  `id UUIDv7 PK, tenant_id FK tenants.id CASCADE NOT NULL,
   user_id FK users.id CASCADE NOT NULL,
   created_at timestamptz NOT NULL, created_by FK users.id SET NULL NULL`.
  Constraints: `uq_tenant_owner(tenant_id, user_id)`,
  `ix_tenant_owners_tenant(tenant_id)`, `ix_tenant_owners_user(user_id)`.
- `memberships.is_primary` stays a UX hint only. Never an auth source.
- Invariants (enforced in service + tests, never in client):
  1. Ownership never grants access. Every request still requires an active
     `memberships` row + `get_ctx` tenant resolution + permission check.
  2. Deactivating an owner `User` never deletes the tenant or its data.
  3. Last-owner protection mirrors last-admin: cannot remove the final
     `tenant_owners` row while tenant is active (extend the ordered-lock
     pattern from `tenancy/service.py:353-365`).
  4. Ownership transfer = insert new owner + audit + (optional) remove old,
     never a client-supplied `user_id` write without server verification.
  5. Tenant scope always server-derived (`get_ctx`, `match_tenant`,
     invitation token lookup). Browser-supplied tenant/user ids are
     selectors at most.

O1 default behavior: one owner per provision (the authenticated verified
caller). Schema supports N owners; multi-owner add/transfer endpoints are
O2 unless the multi-owner release decision is explicitly approved.

## 2. Proposed tables and relationships (DDL sketch, NOT applied)

```sql
-- 0015: public signup verification. Non-RLS, capability-gated.
CREATE TABLE email_verifications (
  id UUID PRIMARY KEY, email TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL, used_at TIMESTAMPTZ NULL,
  attempts INT NOT NULL DEFAULT 0, created_at TIMESTAMPTZ NOT NULL
);
CREATE UNIQUE INDEX ix_verify_pending_email ON email_verifications (lower(email))
  WHERE used_at IS NULL;

-- 0016: commercial ownership. RLS tenant-isolated.
CREATE TABLE tenant_owners (
  id UUID PRIMARY KEY, tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL, created_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
  CONSTRAINT uq_tenant_owner UNIQUE (tenant_id, user_id)
);
ALTER TABLE tenant_owners ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_owners FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_owners_tenant_isolation ON tenant_owners FOR ALL TO hos_app
  USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- 0017: subscription foundation. Plans catalog non-RLS; subscriptions RLS.
CREATE TABLE subscription_plans (
  id UUID PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  max_locations INT NOT NULL, max_practitioners INT NOT NULL,
  max_staff_seats INT NOT NULL, trial_days INT NOT NULL DEFAULT 14,
  is_active BOOLEAN NOT NULL DEFAULT true, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE subscriptions (
  id UUID PRIMARY KEY, tenant_id UUID NOT NULL UNIQUE REFERENCES tenants(id) ON DELETE CASCADE,
  plan_id UUID NOT NULL REFERENCES subscription_plans(id) ON DELETE RESTRICT,
  status TEXT NOT NULL DEFAULT 'trial', trial_ends_at TIMESTAMPTZ NULL,
  period_start TIMESTAMPTZ NULL, period_end TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT ck_sub_status CHECK (status IN
    ('trial','active','past_due','grace','suspended','cancelled','expired'))
);
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions FORCE ROW LEVEL SECURITY;
CREATE POLICY subscriptions_tenant_isolation ON subscriptions FOR ALL TO hos_app
  USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
-- Seed: INSERT INTO subscription_plans (code 'trial-14d', ...) exactly once.
```

What is NOT created in O1: invoice/payment gateway tables, proration
ledgers, metering counters, specialty sets, working-hours tables, branding
storage, support-access grants, `owner_user_id` column.

## 3. Signup and verification architecture

- `POST /auth/signup`: normalize email (`strip().lower()` per
  `identity/service.py:27-28`), validate password (Argon2id, min 12 per
  `platform/security/passwords.py:6`), `create_user` semantics preserved
  (ConflictError path mapped to same 202, no oracle). New
  `email_verifications` row: `raw = secrets.token_urlsafe(48)`,
  store `sha256(raw)`, `expires_at = now + 24h` (proposed), notify request
  `template=verify_email, to_ref=user.id, tenant_id=None` (platform-scoped,
  refs only; delivery via existing dev-console/none adapter — no new
  provider in O1).
- `POST /auth/verify`: lookup by digest; reject missing/used/expired with
  identical `GoneError -> 410`; on success set `used_at`, mark identity
  verified (new `users.email_verified_at` nullable OR verification check
  against `email_verifications` — locked in O1.0; recommended nullable
  column `users.email_verified_at` added in `0015`, default NULL, backfill
  NULL = unverified except bootstrap/platform users treated verified by
  service rule), revoke nothing, audit `auth.verify`.
- `POST /auth/verify/resend`: same 202 always; per-IP throttle
  (`reset:ip` baseline 10/min) + per-email throttle (new limit, proposed
  3/hour) to prevent mailbox bombing; at most one pending row per email
  (upsert-invalidate prior: mark superseded, keep audit).
- Login before verification: allowed to authenticate (existing sessions
  work) but `POST /workspaces` requires verified (403 `email not verified`).
  Rationale: lets users reach "check your inbox" state without lockout,
  while provisioning stays gated.
- Rate limits (new `Settings` keys, O1.1): `SIGNUP_IP_LIMIT_PER_MIN=10`,
  `VERIFY_IP_LIMIT_PER_MIN=10`, `VERIFY_RESEND_EMAIL_LIMIT_PER_HOUR=3`
  (proposed; tuned per deployment like `config.py:80-86`).

## 4. Atomic provisioning sequence (service contract)

Preconditions: `get_current_user` passes; caller `email_verified_at`
not null; `Idempotency-Key` header present and UUID-shaped.
Single `scoped_transaction` (same pattern as `api/deps.py:53-56`):

1. Idempotency check: `workspace_provisions(idempotency_key, user_id)`
   lookup. Hit + same payload hash -> return stored result (201).
   Hit + different hash -> 409. Miss -> insert `pending` row first.
2. Slug: `strip().lower()`, charset `[a-z0-9-]` length 3-63, deny reserved
   (`platform`, `api`, `admin`, `portal`, `login`, `signup`); uniqueness
   check -> 409 on collision (slugs are public; no oracle issue).
3. Timezone: `ZoneInfo(name)` must resolve else 422 (fixes the unvalidated
   `clinics/service.py:24` default for this path; existing locations path
   gets the same validator in O1.2).
4. Insert tenant / `SET app.tenant_id` (server-derived) / insert location /
   insert `tenant_admin` membership (`is_primary=True`) / insert
   `tenant_owners` (caller id only) / insert `subscriptions(trial)` /
   optional practitioner stub / audit appends / outbox enqueue.
5. Mark idempotency `completed` with result refs. Commit. Any exception ->
   rollback all (idempotency row included or left `pending` with TTL for
   safe replay — locked in O1.0; recommended: idempotency table outside
   the provision txn or `pending`-with-expiry so replays are safe).

## 5. Trial subscription design (O1 foundation only)

- Every O1-provisioned tenant gets exactly one `subscriptions` row:
  `plan = trial-14d`, `status = trial`,
  `trial_ends_at = now + plan.trial_days` (14 proposed, D9).
- No card, no charge, no gateway call, no auto-renew job in O1.
- Trial = full operating capability in O1 (no enforcement interlocks).
  Expiry behavior unwired: when `now > trial_ends_at` nothing changes in
  O1 (no downgrade job). Expiry semantics are an O2 decision (see
  unresolved list). A read of subscription status is informational only.
- `Money` pure functions (`billing/money.py`) reused for any amount math
  in future subscription billing; tables never shared (see §7).

## 6. Authorization and RLS design

- Unchanged enforcement: `get_current_user` (identity) ->
  `get_ctx` (tenant + permission + location scope) -> `require(perm)` ->
  `match_tenant` (404 anti-oracle). Ownership adds zero bypass: no endpoint
  checks `tenant_owners` as a substitute for `require(...)`.
- New tables: `email_verifications` non-RLS (capability-gated, like
  `invitations` in `0005_rls.py:53-60`); `tenant_owners` + `subscriptions`
  FORCE RLS tenant-isolated (same `SETTING` expression as `0005_rls.py:24`);
  `subscription_plans` non-RLS readable catalog (like `roles` seed rows),
  writable only via migration/owner role.
- Platform read views use `get_platform_admin` + explicit
  `SET app.tenant_id` to the service-verified target (same pattern as
  `platform.py:38`) for RLS-pinned reads; list endpoints paginate with
  keyset (`limit` capped 100, `cursor` = id) and select only
  tenant/owner-ref/subscription columns.
- Tenant status in O1 stays `active`; `get_ctx:145` continues to refuse
  non-active tenants (fail-closed). No new status writer in O1, so no new
  bypass path.

## 7. Billing separation (hard invariant)

- Clinic billing (`modules/billing/*`, 9 RLS tables in `0009_billing.py`)
  never gains `subscription_id`/`plan_id`; subscription tables never gain
  `patient_id`/`invoice_id`/clinical FKs. Join key across ledgers is
  `tenant_id` only, resolved server-side for reporting.
- Currency discipline identical (Decimal + `quantize_half_up`, INR-only in
  P4) when subscription amounts arrive in O4; no float anywhere.
- No `subscription_*` import inside `modules/billing`; no `billing_*`
  import inside future `modules/subscriptions` except `money` pure functions.

## 8. Threat analysis (abuse cases O1 must handle)

| # | Abuse | Control in O1 |
|---|---|---|
| T1 | Email enumeration via signup/resend | 202 always; identical timing-insensitive path; throttles; no existence signal |
| T2 | Bot mass-signup / mailbox bombing | Per-IP signup + per-IP/per-email resend throttles; 24h TTL; single pending row per email; CAPTCHA deferred (note as residual) |
| T3 | Verification token guessing (256-bit) | `token_urlsafe(48)`, sha256 stored, 410 indistinguishable, IP throttle, single-use |
| T4 | Unverified provisioning | Service-level verified check; 403 before any write |
| T5 | Tenant slug squatting / impersonation | Charset + reserved list + uniqueness; availability check authenticated-only in O1.5 if added |
| T6 | Tenant-creation abuse (one user, N tenants) | Per-user provision throttle (proposed 5/day) + audit; hard quota deferred to O2 plan limits |
| T7 | Ownership hijack via client `user_id`/`owner` fields | No such fields accepted; owner always `ctx.user_id`; transfer endpoint does not exist in O1 |
| T8 | Cross-tenant read via forged X-Tenant/UUID | `get_ctx` membership match + `match_tenant` 404; new tables RLS-pinned; isolation tests |
| T9 | Privilege escalation via role name | Role resolution server-side (`_role_by_name` pattern); `validate_custom_role` blocks platform perms; owner always gets seed `tenant_admin`, never caller-chosen role string in O1.2 |
| T10 | Session fixation on invite/verify accept | Fresh `issue_session_pair` on verify-then-login only; no auto-login on verify in O1 (recommended); rotation + reuse detection unchanged |
| T11 | Payment / notification injection | No gateway or provider in O1; notify path refs-only via existing eligibility gate; `SUPPORT_GRANT` unwired |
| T12 | RLS bypass via new tables | FORCE RLS + least-privilege grants from migration; `ops.py:APP_TABLES` extended; `test_rls`-style negative tests for new tables |
| T13 | Audit tampering on provision | Append-only `audit_events` (revoked UPDATE/DELETE per `0005_rls.py:85`); provision emits refs-only events |

Residual risks (accepted in O1, tracked): no CAPTCHA/anti-bot beyond
throttles; no SLA on verification-mail delivery (dev-console/none);
single-region idempotency TTL; support-access flow absent (no break-glass
in O1 — platform admins cannot read clinical data, same as today per
`platform.py:1-3`).
