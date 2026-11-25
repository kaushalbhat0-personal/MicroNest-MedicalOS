# P3.7C.1 — Privilege Audit & Positive Billing Verification

**Date:** 2026-11-24  
**Final verdict:** **CONDITIONAL PASS**

Preserves P3.7C artifacts unchanged:
- `docs/deployment/P3-7C-synthetic-tenant-isolation-report.md`
- `scripts/_p37c_evidence.json`

New evidence (this phase only):
- `scripts/_p37c1_privilege_audit.json`
- `scripts/_p37c1_billing_evidence.json`
- Alignment helper: `scripts/_p37c1_align_seed_roles_0021.py`

---

## 1. Deployment SHA and staging database identity

| Field | Value |
|-------|-------|
| API | `https://micronest-medicalos.onrender.com` |
| Deploy commit | `293dc668e7117f20a4b88e7a3047aa8e501c99b6` |
| Database | `healthcare_os_preview` |
| Host shape | `aws-1-eu-west-3.pooler.supabase.com` (session pooler) |
| Alembic | `0027_saas_payment_reliability` |
| Runtime role | `hos_app` |
| Migrator role | `hos_owner` |
| Platform admin role | `postgres` (Supabase) |

Credentials and connection strings are not reproduced here.

---

## 2. Role attribute matrix (live staging)

| Role | LOGIN | SUPERUSER | BYPASSRLS | CREATEDB | CREATEROLE |
|------|-------|-----------|-----------|----------|------------|
| `postgres` | yes | **false**\* | **true** | true | true |
| `hos_owner` | yes | **false** | **true** | false | false |
| `hos_app` | yes | **false** | **false** | false | false |
| `authenticator` | yes | false | false | false | false |
| `anon` / `authenticated` | no | false | false | false | false |

\*Supabase `postgres` is not `rolsuper` but retains elevated capabilities including `BYPASSRLS`.

**No privilege changes were made in this phase** beyond completing seed-role JSON alignment (application permission bundles, not PostgreSQL role attributes). `hos_owner BYPASSRLS` remained as established in P3.7C; it was **not** revoked and **not** newly granted here.

---

## 3. Schema / table ownership and privilege summary

| Finding | Evidence |
|---------|----------|
| Public base tables | **75** |
| Table owner | **all** owned by `hos_owner` |
| `hos_owner` on `public` | USAGE + CREATE |
| `hos_app` on `public` | USAGE; **CREATE denied** |
| `hos_app` DML on clinical/billing tables | SELECT/INSERT/UPDATE/DELETE where granted (e.g. `estimates`, `invoices`, `payments`, `patients`, `treatment_plans`) |
| `hos_app` on `alembic_version` | **no SELECT/UPDATE** (revision mutation denied) |
| Default privileges (`pg_default_acl`) | **empty** — future objects rely on explicit migration `GRANT`s |
| Role memberships of concern | `hos_app` / `hos_owner` are **not** members of each other; no escalation via `pg_auth_members` |

---

## 4. RLS and FORCE RLS findings

| Metric | Value |
|--------|-------|
| Tables with RLS enabled | 57+ tenant tables |
| Tables with **FORCE RLS** | **57** |
| `alembic_version` RLS | off (expected; protected by grants instead) |
| `roles` RLS + FORCE | **on** (global seed rows `tenant_id IS NULL`) |
| SECURITY DEFINER functions in `public` | **0** |

`hos_app` without `app.tenant_id`:
- `locations` count = **0**
- `patients` count = **0**

Cross-tenant API regression (live): Owner A + `X-Tenant: B` → **403**; Owner B + `X-Tenant: A` → **403**.

---

## 5. Seed-role repair explanation and repeatability

### Root cause (confirmed)

1. Migration `0002` inserts global seed roles (`tenant_id IS NULL`).
2. Migration `0005` enables **FORCE RLS** on `roles`.
3. Later migrations (`0008`–`0021`) run `UPDATE roles SET permissions=… WHERE tenant_id IS NULL` as `hos_owner`.
4. With `hos_owner BYPASSRLS=false`, those UPDATEs matched **0 rows** under FORCE RLS, while Alembic still advanced to `0027`.
5. Result: `tenant_admin` stuck at the 0002 baseline (7 perms, no `patient.create`) until P3.7C repair.

### P3.7C repair (prior phase)

- Platform `postgres` granted `ALTER ROLE hos_owner BYPASSRLS`.
- Seed permission JSON re-applied, but using a **non-canonical** permission set (included bogus `refund.create` / `credit.*` / `clinical.amend`; **missing** `plan.manage`, `billing.refund`, `billing.config`, `inventory.purchase`).

### P3.7C.1 completion (this phase)

Re-aligned global seed roles to the **exact** `ROLE_PERMS` from `backend/alembic/versions/0021_inventory.py` via `scripts/_p37c1_align_seed_roles_0021.py`.

| Check | Before align | After align |
|-------|--------------|-------------|
| `tenant_admin` count | 39 | 39 |
| `patient.create` | true | true |
| `plan.manage` | **false** | **true** |
| `billing.refund` | false | true |
| `refund.create` (bogus) | **true** | **false** |
| Matches 0021 exactly | no | **yes** |

Removed from prior incomplete repair: `clinical.amend`, `credit.allocate`, `credit.issue_note`, `refund.create`.  
Added: `plan.manage`, `billing.refund`, `billing.config`, `inventory.purchase`.

### Is `hos_owner BYPASSRLS` necessary?

**Yes, for the current migration design.** Seed/reference UPDATEs and owner DML against FORCE RLS tables have no `TO hos_owner` policies. Options:

1. **Keep `hos_owner BYPASSRLS`** (local parity; current staging) — recommended.
2. Or add explicit owner policies / run seed UPDATEs only as `postgres` — larger migration redesign.

**Do not revoke** without an approved migration-policy redesign.  
**Do not grant BYPASSRLS or SUPERUSER to `hos_app`.**

### Repeatability

1. Run migrations as `hos_owner` **with BYPASSRLS=true** (or as `postgres` for seed UPDATEs).
2. After any role-permission migration, verify:
   `SELECT name, permissions ? 'plan.manage', permissions ? 'patient.create' FROM roles WHERE tenant_id IS NULL;`
3. If drift is detected, re-run `scripts/_p37c1_align_seed_roles_0021.py` (idempotent) against staging only.
4. Empty `pg_default_acl` means **every new table migration must continue to `GRANT` to `hos_app` explicitly**.

Survives a fresh migrate only if migrator can see/update FORCE RLS seed rows (BYPASSRLS or postgres).

---

## 6. `hos_app` least-privilege evidence

| Probe | Result |
|-------|--------|
| `rolbypassrls` | **false** |
| `CREATE TABLE` | **DENIED** |
| `UPDATE alembic_version` | **DENIED** |
| `SELECT alembic_version` | **DENIED** |
| Tenant tables without `app.tenant_id` | **0 rows** |
| Live API cross-tenant header swap | **403** |
| Billing artifact cross-tenant GET | **404** (path) / **403** (header) |

Isolation was **not** weakened by seed-role JSON alignment (permissions are application-layer bundles read by `require()`, not DB role attributes).

---

## 7. Positive billing workflow (Tenant A, live API)

Synthetic Clinic Alpha owner session; synthetic patient; manual cash payment (no payment provider).

| Step | Route | Expected | Actual | Result |
|------|-------|----------|--------|--------|
| B1 Create treatment plan | `POST /treatment-plans` | 200 draft | 200 `draft` | PASS |
| B2 Activate plan | `POST …/activate` | 200 `active` | 200 `active` | PASS |
| B3 Create estimate (2 lines, linked to plan) | `POST /estimates` | 200 | 200, lines=2 | PASS |
| B4 Totals | — | `grand_total=1750.00` INR | 1750.00 INR | PASS |
| B5 Issue estimate | `POST …/issue` | `issued` | `issued` | PASS |
| B6 Convert to invoice | `POST …/convert` | draft invoice | `draft` 1750.00 | PASS |
| B7 Issue invoice | `POST /invoices/{id}/issue` | `issued` | `issued` | PASS |
| B8 Balance | `GET /invoices/{id}` | outstanding 1750.00 | `outstanding_amount=1750.00` | PASS |
| B9 Record payment | `POST /payments` method=`cash` | recorded | `cash` 1750.00 `recorded` | PASS |
| B10 Allocate | `POST /payments/{id}/allocations` | 200 | 200 | PASS |
| B11 Paid | `GET /invoices/{id}` | paid / 0 due | `status=paid` | PASS |
| B12 Timeline | `GET …/timeline` | billing events | 4 items, billing_hit=true | PASS |

Evidence: `scripts/_p37c1_billing_evidence.json` (28 PASS / 0 FAIL).

---

## 8. Tenant A/B billing isolation

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| B GET A estimate (path A, hdr B) | 404 | 404 | PASS |
| B GET A estimate (hdr A) | 403 | 403 | PASS |
| B GET A invoice (path A, hdr B) | 404 | 404 | PASS |
| B GET A invoice (hdr A) | 403 | 403 | PASS |
| B GET A payment (path A, hdr B) | 404 | 404 | PASS |
| B GET A payment (hdr A) | 403 | 403 | PASS |

---

## 9. Email test convention findings

| Topic | Finding |
|-------|---------|
| Why `example.test` fails | `email-validator` (used by Pydantic `EmailStr`) rejects RFC 6761 special-use / reserved TLDs such as `.test`, `.invalid`, `.localhost` (“special-use or reserved name that cannot be used with email”). |
| Current staging convention | Synthetic addresses under **`@example.com`** (RFC 2606 documentation domain). |
| Production policy | **Do not weaken** `EmailStr` / deliverability rules for tests. |
| Recommended options | (a) keep `@example.com` for non-delivery API tests; (b) for real inbox flows, use a **controlled mail sink** (project-owned test domain or provider sandbox) with `NOTIFY_PROVIDER` configured — not wildcard validation. |
| Change proposal | **None in this phase.** Domain policy unchanged. |

---

## 10. Skipped tests

None in the executed P3.7C.1 suite (privilege audit + billing matrix).  
Original P3.7C report remains authoritative for prior 59-test isolation suite.

---

## 11. Risks and recommended remediation

1. **Migration/seed under FORCE RLS** — keep `hos_owner BYPASSRLS`; add a post-migrate check for seed role permission drift.
2. **Empty default privileges** — every new table migration must `GRANT` to `hos_app` explicitly (already the pattern).
3. **Incomplete first repair** — always align to the latest migration `ROLE_PERMS` source of truth (`0021` today); prefer extracting shared constants later (out of scope; no app code changes this phase).
4. **Shared S3 credential** — unchanged from P3.7C; still not per-tenant IAM.
5. **`NOTIFY_PROVIDER=none`** — email verification/reset still not deliverable on staging.

**No further PostgreSQL privilege changes proposed.** If a future change is desired (e.g. owner RLS policies instead of BYPASSRLS), it requires a separate approved SQL plan with blast radius and rollback.

---

## 12. Verdict

### **CONDITIONAL PASS**

**PASS because:**
- Live privilege audit confirms `hos_app` least privilege (no BYPASSRLS, no DDL, no Alembic mutation, RLS zero-rows without tenant).
- Seed roles aligned to canonical 0021 bundles; `plan.manage` / `patient.create` verified via API.
- Positive treatment-plan → estimate → invoice → cash payment → allocate → paid workflow executed on staging API.
- Cross-tenant billing isolation holds; P3.7C evidence preserved.

**Conditional because:**
- Staging still depends on `hos_owner BYPASSRLS` for migration/seed correctness (documented necessity, not revoked).
- Storage IAM limitation from P3.7C remains.
- Email delivery path remains unproven (`NOTIFY_PROVIDER=none`).
