# P3.7C — Synthetic Tenant Isolation Report

**Date:** 2026-11-24  
**Final verdict:** **CONDITIONAL PASS**

Authenticated cross-tenant isolation and core synthetic workflows succeeded on the live Render staging API after a required staging seed-role repair. Per-tenant object-storage IAM is **not** claimed.

---

## 1. Test environment and deployment SHA

| Field | Value |
|-------|-------|
| API | `https://micronest-medicalos.onrender.com` |
| Render service | `MicroNest-MedicalOS` (`srv-dc2tmb49v7es73dkqc9g`) |
| Branch | `release/p3-7b-staging` |
| Auto-deploy | disabled |
| Deploy commit | `293dc668e7117f20a4b88e7a3047aa8e501c99b6` |
| Database | Supabase `healthcare_os_preview`, Alembic `0027_saas_payment_reliability` |
| Runtime DB role | `hos_app`, `BYPASSRLS=false` |
| Storage | Private Supabase S3-compatible bucket `dental-os` |
| Evidence artifact | `scripts/_p37c_evidence.json` (redacted) |
| Credentials artifact | `.env.p37c.staging` (gitignored; never committed) |

---

## 2. Synthetic tenant / account setup (no secrets)

| Clinic | Slug | Owner email pattern | Role |
|--------|------|---------------------|------|
| Synthetic Clinic Alpha | `synth-clinic-alpha-f9ca69` | `p37c.owner.alpha.f9ca69@example.com` | `tenant_admin` |
| Synthetic Clinic Beta | `synth-clinic-beta-f9ca69` | `p37c.owner.beta.f9ca69@example.com` | `tenant_admin` |

Additional synthetic identities (passwords only in gitignored artifact):

- Receptionist Alpha (`receptionist`) via invite accept API token (one-time; not logged).
- Portal users A1 / A2 — signup with password, then staff `portal-links` enroll (existing credentials retained).

**Email domain note:** Requested `example.test` addresses are rejected by application `EmailStr` / `email-validator` (“special-use or reserved name”). Synthetic addresses use RFC 2606 `example.com` instead. Auth was not weakened.

**Supported flows used (no invented endpoints):**

1. `POST /api/v1/auth/signup` → `POST /api/v1/auth/login` (email verification **not** required for login/workspace).
2. `POST /api/v1/workspaces` + `Idempotency-Key` (no `X-Tenant`).
3. `POST /api/v1/tenants/{id}/verification` `{status: approved}` with `X-Tenant`.
4. `POST /api/v1/tenants/{id}/invites` → `POST /api/v1/invites/accept`.
5. Patients / appointments / encounters / documents / portal / follow-ups / WhatsApp link as documented in code.

Tenant header name is **`X-Tenant`** (not `X-Tenant-Id`).

### Staging prerequisite repair (ops, not auth bypass)

Initial owner workspaces provisioned, but `tenant_admin` seed permissions were stuck at migration `0002` baseline (7 perms; **no** `patient.create`). Cause: after `FORCE ROW LEVEL SECURITY` on `roles`, later Alembic `UPDATE roles … WHERE tenant_id IS NULL` ran as `hos_owner` with `BYPASSRLS=false` and updated **0 rows**, while `alembic_version` still reached `0027`.

Controlled staging remediation (documented P3.7A recommendation):

1. Connected as Supabase platform `postgres` (has `BYPASSRLS`).
2. `ALTER ROLE hos_owner BYPASSRLS` (**not** `hos_app`).
3. Re-applied cumulative global seed role permission bundles (from migration `0021` ROLE_PERMS).

`tenant_admin` afterward: 39 permissions including `patient.create`. Application authorization paths unchanged.

---

## 3. Test matrix (expected vs actual)

Machine-readable detail: `scripts/_p37c_evidence.json`.  
**Counts:** PASS=59 · FAIL=0 · SKIP=0 (executed suite).

### Provisioning

| ID | Expected | Actual | Result |
|----|----------|--------|--------|
| P3_A/B_provision | workspace 201 + practitioner approved | 201 | PASS |
| P3_A/B_me_tenants | each owner sees only own tenant | count=1, no cross | PASS |
| P3_A_invite_recv / accept / login | invite + accept + login | 200 | PASS |
| P3_patients_created | A×2 + B×1 synthetic patients | 201 | PASS |

### Cross-tenant API isolation

| ID | Expected | Actual | Result |
|----|----------|--------|--------|
| C1/C2 own patient read | 200 | 200 | PASS |
| C3/C4 path/header swap | 404 path mismatch / 403 unknown tenant | 404 / 403 | PASS |
| C5 search | no foreign tenant rows | 200, B id absent | PASS |
| C6 appointments create/list/cross | 200 create; A list excludes B; B header → 403 | as expected | PASS |
| C7 encounter/note/doc/billing cross | own OK; cross 404/403 | as expected | PASS |
| C8/C9 aggregate header swap | fail-closed | PASS | PASS |
| C10 missing/invalid/logout | 401 | 401 | PASS |
| C11 receptionist owner-only ops | 403 on verification + invite | 403 | PASS |

### Portal isolation

| ID | Expected | Actual | Result |
|----|----------|--------|--------|
| C12 enroll + login + `/portal/me` | 200 | 200 | PASS |
| C12 staff patient route as portal | 403 | 403 | PASS |
| C12 foreign portal encounter | 404 | 404 | PASS |
| C12 `X-Tenant` = B | 403 | 403 | PASS |

### Core workflow (Tenant A)

| ID | Expected | Actual | Result |
|----|----------|--------|--------|
| W1 patient search | 200 contains A1 | PASS | PASS |
| W2 calendar list | 200 | PASS | PASS |
| W3 check-in + reception queue | 200 | PASS | PASS |
| W4 overview + timeline | 200 | PASS | PASS |
| W5 prescription | 200 if catalog allows | 200 | PASS |
| W6 follow-up + consent + WhatsApp link | 200, `auto_send=false` | PASS | PASS |

### Storage

| ID | Expected | Actual | Result |
|----|----------|--------|--------|
| S1 server key tenant prefix | `tenants/{A}/…` | PASS | PASS |
| S2 signed fetch | 200 synthetic bytes | PASS | PASS |
| S3 expired | 400/401/403 | 400 | PASS |
| S4 tampered | 400/401/403/404 | 403 | PASS |
| S5 public URL | denied | 403 | PASS |
| S6 shared cred reads B key | EXPECTED_ACCOUNT_SCOPE | PASS | PASS |
| S7 IAM claim | do not claim per-tenant IAM | PASS | PASS |

---

## 4. Cross-tenant API isolation evidence

- Owners authenticate independently; `/auth/me` shows a single tenant each.
- `X-Tenant` selecting the other clinic without membership → **403** `unknown tenant`.
- Path tenant ≠ resolved context → **404** `not found` (`match_tenant`).
- Patient search, appointment lists, encounter/document/estimate access never returned foreign-tenant records.
- Evidence rows: `C1`–`C9` in `_p37c_evidence.json`.

---

## 5. Patient portal isolation evidence

- Portal users created via supported signup + password; enrolled with `POST …/portal-links`.
- Portal session reaches `/portal/me` under Tenant A only.
- Portal identity cannot use staff patient routes (403) or foreign encounter IDs (404).
- Portal + `X-Tenant: B` → 403.
- Patient `patient_id` for portal is server-derived from the portal link (not client-supplied).

---

## 6. Role / permission checks

| Check | Result |
|-------|--------|
| Owner (`tenant_admin`) can approve practitioner, invite, clinical, billing read paths used | PASS |
| Receptionist cannot `POST …/verification` | **403** PASS |
| Receptionist cannot `POST …/invites` | **403** PASS |
| Anonymous / invalid bearer / post-logout | **401** PASS |

---

## 7. Storage isolation evidence and limitations

| Layer | Status |
|-------|--------|
| Application authorization before document access mint | **PASS** (cross-tenant 403/404) |
| Server-allocated tenant-prefixed object keys (P3.6) | **PASS** |
| Signed URL expiry + tamper resistance | **PASS** |
| Public object URL denial | **PASS** |
| Per-tenant IAM / bucket policy isolation | **NOT ACHIEVED** — shared account/bucket S3 credential can read any key (`S6`) |

Isolation depends on API auth + server key allocation, not provider IAM prefixes.

---

## 8. Core workflow results

Tenant A exercised: patient register/search, appointment + check-in + reception queue, patient 360 overview/timeline, clinical note, prescription, follow-up, communication consent, user-initiated WhatsApp link (`auto_send=false`, no send), synthetic document create + authorized signed access.

Tenant B: patient + appointment + enough records to prove isolation (not a full workflow duplicate).

**Not fully exercised in this run:** end-to-end dental treatment-plan → estimate → invoice issue chain (billing **cross-tenant deny** was tested via estimates list). Optional follow-up.

---

## 9. Failed, skipped, blocked

| Item | Status | Reason |
|------|--------|--------|
| Suite failures | **none** | 59/59 PASS |
| `example.test` emails | **adapted** | EmailStr rejects reserved `.test`; used `example.com` |
| Seed role permissions pre-repair | **blocked then repaired** | See §2 ops remediation |
| Full treatment-plan/invoice happy path | **not run** | Optional; isolation for estimates covered |
| Email verification delivery | **N/A** | Not required for login/workspace; `NOTIFY_PROVIDER=none` |

---

## 10. Cleanup performed

- Synthetic document **object** for Tenant A deleted from bucket after storage tests.
- Synthetic clinics, users, patients, appointments, encounters **left in staging** for auditability (clearly named `Synthetic*` / `p37c.*@example.com` / slug tag `f9ca69`).
- Invite raw tokens never written to docs or evidence JSON.
- Passwords only in gitignored `.env.p37c.staging`.

---

## 11. Remaining security blockers / risks

1. **Seed-role migration under RLS** — staging needed a one-time postgres repair; future cloud migrations as `hos_owner` now have `BYPASSRLS` (ops parity). Re-verify seed perms after any role-permission migration.
2. **Shared S3 credential** — not per-tenant IAM.
3. **`NOTIFY_PROVIDER=none`** — no real email delivery for verify/reset; portal activation used signup-before-enroll pattern instead of reset email.
4. **Vercel frontend origin** still unset; CORS remains API-self-origin only (not wildcard).
5. Earlier aborted provision attempt left orphan synthetic users/tenants from tag `298012` (incomplete permissions era) — harmless clutter; optional cleanup later.

---

## 12. Final verdict

### **CONDITIONAL PASS**

**Why PASS:** Live staging authenticated isolation, role boundaries, portal isolation, core synthetic clinic workflows, and storage app-layer controls all executed successfully (59/59).

**Why conditional:**

1. Required staging ops repair of seed roles + `hos_owner BYPASSRLS` before workflows could run.
2. Storage isolation is application/key-based, **not** per-tenant IAM.
3. Full dental plan → invoice chain not re-proven in this pass.

**Real patient data:** remains blocked — only synthetic identities/content used; no production deploy; `hos_app` still has no BYPASSRLS / no DDL.
