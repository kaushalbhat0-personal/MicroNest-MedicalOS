# P1.5 Commercial Readiness Audit (evidence-based)

**Scope:** Audit only. No subscription/billing platform implementation in P1.5.  
**Baseline HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**Date:** 2026-11-24  
**Supplement:** Findings reconciled with deep audit of tenancy/subscriptions/portal/deps (see agent [Commercial readiness audit](f3a85af5-5179-4fc1-b4e6-3d494bad3ce1)).

No regulatory compliance claims are made from architecture alone.  
Note: `docs/commercial/customer-onboarding-architecture.md` is partly stale (signup/workspaces/subscriptions now exist).

---

## B1 — Tenant and account lifecycle

| Capability | Status | Evidence | Gaps |
|------------|--------|----------|------|
| Signup | Implemented + verified | `api/v1/signup.py` (`POST /auth/signup` → 202); `apps/web/app/signup` | Production email: `NOTIFY_PROVIDER` ∈ `{dev-console, none}` only (`platform/config.py`) |
| Email verification | Partial | `identity/verification.py`; `0015_signup_verification`; consume sets `email_verified_at` | Optional for workspace provision (`require_verified_email` unused in prod paths). No email-change flow |
| Workspace provisioning | Implemented + verified | `workspaces/service.py` `provision_workspace`; atomic tenant → location → membership → owners → practitioner → specialties → trial → audit → outbox | Single location at create; no paid checkout |
| Tenant ownership | Partial | `TenantOwner` + RLS in `0016`; created at provision | No owner add/transfer/remove APIs; last-owner deferred (O2 docs) |
| Multiple memberships | Implemented + verified | UNIQUE `(user_id, tenant_id)`; `X-Tenant` when >1 membership (`deps.get_ctx`) | — |
| Staff invitations (accept) | Implemented + verified | `tenancy` create + `api/v1/invites.py`; authenticated accept adds membership | Delivery depends on notify adapters |
| Staff invitations (revoke) | Implemented | `staff/service.revoke_invitation`; `api/v1/staff.py` | — |
| Last-admin protection | Implemented + verified | `update_membership` blocks removing last `staff.manage` with `FOR UPDATE`; concurrent demotion tests | — |
| Last-owner protection | Missing | Documented deferred | `is_primary` is UX hint only — not a guard |
| Tenant status / suspension | Partial | Status enum; `set_tenant_status`; `get_ctx` refuses `status != active`; permission `platform.tenant.suspend` seeded | **No API** calls `set_tenant_status` (platform console GET-only). Permission unwired. Do not conflate with `subscriptions.status` |
| User deactivation / deletion | Missing (field only) | `User.is_active` checked on login/session | No deactivate/delete user API; no erasure/cascade product policy |
| Location create | Implemented | `clinics/service.create_location` + `POST .../locations` | — |
| Location deactivate | Missing (column only) | `Location.is_active`; writes refuse inactive locations | **No deactivate/update-location API** |
| Orphaned membership | Missing | CASCADE FKs + last-admin on demote | No job/API for owner-without-membership, inactive user with memberships, dangling invites |

**Material missing safeguards:** enforced seat/location limits; subscription grace; distinct abuse-suspend vs billing-lapse; portal continuity under commercial lapse; export/deletion APIs; wired suspend API; location deactivate API; last-owner guard.

---

## B2 — Subscription / entitlement gap matrix

| Capability | Existing implementation | Missing work | Risk | Recommended phase |
|------------|-------------------------|--------------|------|-------------------|
| Subscription / customer models | `subscriptions` + `subscription_plans`; 1:1 tenant (`uq_subscriptions_tenant`); `0016` | `subscription_customers`, SaaS invoices/payments, provider customer ids | Medium | P2.1 |
| Plans | Seeded `trial-14d` (max_locations=3, max_practitioners=10, max_staff_seats=25) | Paid catalog; versioning beyond migrate-only | Medium | P2.1 |
| Entitlements | Plan columns + `PlanLimits` with **`enforced=False`** (`build_summary`) | Server entitlement resolver; enforce on create/invite/location | **High** — caps cosmetic | P2.2 |
| Feature flags | None as commercial flags; specialty packs are separate (`workspaces/registry.py`) | SKU / feature matrix | Medium | P2.3+ |
| Billing integration (SaaS) | Separated from clinic AR by design | Platform subscription ledger | **High** | P2.4 |
| Payment provider | **None** — no Razorpay/Stripe/etc. in code | Provider adapter + secrets + test mode | **High** | P2.4 (choose then abstract) |
| Webhooks | None for SaaS | Signed endpoint + idempotency ledger | **High** | P2.4 |
| Lifecycle | Enum includes trial/active/past_due/grace/suspended/cancelled/expired; only **trial** written | Transitions + expiry jobs | **High** | P2.2–P2.3 |
| Trial | 14-day row at provision; `is_in_trial` derived read-only | Expiry enforcement; convert-to-paid | High | P2.2 |
| Seat / location / usage limits | On plan + summary only | Atomic reservation on invite accept / location create | **High** concurrent oversell | P2.2 |
| Grace | Status token only | Clock, banner, invite gates | Medium–High | P2.3 |
| Cancel / renew | Status values only | APIs + period boundaries | Medium | P2.5 |
| Failed payment | `past_due` enum only | past_due → grace → commercial suspend | **High** | P2.4–P2.5 |

Clinic patient billing (`modules/billing/`) is **not** SaaS subscription billing — keep ledgers separate.

---

## B3 — Multi-tenant commercial isolation

| Question | Finding |
|----------|---------|
| Multi-clinic membership | Yes — one user, N memberships; invite-auth accept; `X-Tenant` when >1. |
| Per-membership roles | Yes — `Membership.role_id` → permissions; `require(permission)`. |
| Location assignments | Relational `membership_locations`; empty = all locations; services take `location_ids`. Helper `may_access_location` exists but is **unused**. |
| Tenant data isolation | Strong: RLS FORCE + `set_config('app.tenant_id')`; isolation / two-pilot suites. |
| Entitlement scoping | Per-`tenant_id` data model; **no request-time entitlement gate**. |
| Concurrent seat/location limits | **Unsafe** — `enforced=False`; no lock/count on invite accept or location create. |
| Suspended tenants vs portal | **Coupled — portal locked out today.** `get_ctx` raises if tenant not active; portal uses `require(P.PORTAL_READ)` → same gate. Invite accept also refuses inactive tenants. Link creation requires `TENANT_ACTIVE`. |
| Before subscriptions | Keep clinic AR separate. Enforce entitlements only on create/invite paths. **Split** `tenants.status` (abuse) from `subscriptions.status` (commercial). Decouple portal reads from commercial lapse before monetization. |

---

## B4 — Security / operational readiness

| Area | Status | Evidence | Notes |
|------|--------|----------|-------|
| Auth / session | Implemented + verified | Login, refresh rotation, reuse detection; cookies/Bearer | — |
| Password reset | Implemented + verified (eng) | `api/v1/account.py`; hashed tokens; no-oracle 202 | Delivery limited by notify provider |
| Email verification | Partial | Challenge lifecycle exists | Production delivery absent |
| Authorization / RLS | Implemented + verified | `require()`; RLS FORCE; isolation tests | Registry tables intentionally non-RLS |
| Audit logs | Implemented + verified | Hash-chained audit; append-only for app role | Ops dashboard GET unaudited by design |
| Outbox | Implemented; prod path not fully verified | Outbox + worker; provision/notify | Real providers deferred |
| Secrets / env | Implemented (eng) | ENV×DEPLOYMENT validation; JWT length; scrubbing | Not a compliance attestation |
| Backup / restore | Partial | `docs/database/p7-operations.md`; `scripts/backup-preview.sh` | RPO/RTO not proven for prod schedules |
| Logging | Implemented | PHI/secret scrubbing; security headers | — |
| Rate limiting | Partial | In-memory limiter on signup/login/invite/verify | Not distributed |
| Retention / deletion | Not implemented | D4 unresolved in commercial docs | **Requires legal/security assessment** |
| Export / portability | Not implemented | `reports.export` permission exists; no export API | Same legal caveat |
| Cross-tenant tests | Implemented + verified | Isolation + O1.5R + workspace RLS tests | — |
| Production deploy | Partial | `config.py` profiles; deployment docs | Managed PG, SES, secrets external |
| Regulatory compliance | Requires legal/security assessment | Product security review disclaims HIPAA/GDPR/DPDP claims | **No claim** |

---

## B5 — Recommended staged commercial architecture (do not implement yet)

**Clinic tenant** = SaaS customer. **Patients** = portal end users of the clinic — not SaaS subscribers.  
**Do not** lock portal solely because clinic subscription lapsed.

1. **Ownership:** Keep `subscriptions` 1:1 tenant; `tenant_owners` as commercial authority. Add owner transfer + last-owner guard (mirror last-admin).
2. **Plans / entitlements:** Versioned plan catalog; tenant entitlement snapshot updated only by server/webhook; app never calls payment API per request.
3. **Seats / locations:** Count active memberships (decide if pending invites reserve seats). Enforce at invite create/accept and location create with tenant-row lock — not count-then-insert under READ COMMITTED alone.
4. **Trial / grace / transitions:** `trial → active → past_due → grace → suspended → cancelled|expired`. Server-only + audited. Grace: block usage-expanding writes; preserve clinical + portal reads + export.
5. **Payment provider abstraction:** Port + adapter; choose provider in P2 — **none assumed**. Never share clinic invoice tables.
6. **Webhook idempotency:** UNIQUE provider event id; one txn with subscription transition + outbox; safe replay.
7. **Failed payment:** Webhook → `past_due` → grace → `subscriptions.status=suspended`. **Do not** set `tenants.status=suspended` for billing lapse.
8. **Abuse suspend:** `tenants.status=suspended` remains staff hard lock; wire `platform.tenant.suspend` to API separately from commercial suspend.
9. **Portal during lapse:** Allow portal reads of permitted records when subscription is past_due/grace/suspended; block new portal enrollments and staff commercial mutations only. **Today’s coupling must change before monetization.**

---

## Recommended P2 sequence

1. **P2.0 — Gate design freeze** — Portal-vs-clinic access matrix; map `subscription.status` ↔ `tenant.status`; seat/grace definitions (unblocks wrong `get_ctx` coupling).
2. **P2.1 — Plan catalog + entitlement read model** — Paid plans; snapshot; shadow-mode logging optional.
3. **P2.2 — Enforce limits** — Atomic location/seat/practitioner caps; trial expiry → grace/suspend; concurrent oversell negative tests.
4. **P2.3 — Decouple portal from commercial suspend** — Portal read path independent of billing lapse; staff write gates remain; platform abuse-suspend API.
5. **P2.4 — Payment provider + webhooks** — Checkout; signed webhooks; idempotency; active/past_due; provider chosen then abstracted.
6. **P2.5 — Dunning, cancel/renew, owner transfer** — Real email provider; last-owner + transfer; owner-only failed-payment UX.
7. **P2.6 — Ops / compliance enablement** — Backup drills; retention/export; distributed rate limits — legal review before marketing claims.
8. **P2.7 — Staff Playwright ops suite** — Currently missing (`docs/product/p15-operations-e2e.md`).

**Already solid to build on:** signup, atomic workspace+trial, memberships/invites/revoke, last-admin, RLS+isolation tests, clinic billing isolation, audit/outbox, config profiles.
