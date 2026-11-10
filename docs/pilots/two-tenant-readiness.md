# Two-tenant pilot readiness — Tenant A (dental) + Tenant B (eye)

Status: readiness assessment on synthetic data. No production onboarding claimed.
No real doctor identities, credentials, or patient data. No schema changes.
Companion test: `tests/isolation/test_p8_two_tenant_pilots.py` (repeatable,
uses existing fixtures against the isolated TEST database only).

## 1. Readiness verdict

READY for synthetic pilot simulation on existing primitives; NOT ready for
production onboarding. Tenant isolation holds across patients, appointments,
clinical records, billing, documents (metadata), portal links, and audit
(existing + new P8 test evidence). Branding, notifications, subscriptions, and
licensing remain stubs — pilot expectations must be set accordingly.

## 2. Verified capabilities (with evidence)

| Capability | Implementation | Evidence |
|---|---|---|
| Independent tenant creation | `tenancy.create_tenant` (slug unique, active status) | P8 test: two tenants, distinct ids/slugs |
| Clinic/location config | `clinics.create_location` per tenant, name-unique-in-tenant | P8 test: Main + Annex per tenant, cross-tenant location rejected (403/404) |
| Doctor membership | user + practitioner + verification-approved + doctor role | P8 test: per-tenant doctor, unverified practitioner blocked (existing clinical tests) |
| Staff membership | receptionist / staff roles, location-scoped memberships | P8 test: receptionist in A cannot read B; location scope enforced |
| Role bundles | `SEED_ROLES` (tenant_admin/doctor/receptionist/nurse/accountant/staff/patient) + custom-role subset validation | `tests/unit/test_permissions.py`, P8 dual-role check |
| Location scope | `location_ids` on RequestContext, enforced in scheduling/clinical/dental/billing reads + writes | P8 scoped-doctor checks; `test_clinical_isolation.py` |
| Patient creation | `patients.register_patient`, tenant-pinned reads (404 oracle) | P8 cross-patient read 404 |
| Appointment creation | future-start, double-book guard, idempotency, verified-practitioner gate | P8 cross-tenant appointment read 404 |
| Clinical access | encounter open/close ceremony, note finalize/amend chains, tenant-pinned getters | P8 cross-encounter/note 404 |
| Billing isolation | estimates/invoices tenant-pinned, idempotency per tenant, cross-convert 404 | P8 invoice cross-read 404; `test_billing_invoices_api.py::test_idor_and_location_scope` |
| Portal enrollment | staff-gated `POST /tenants/{id}/portal-links`, link pins user+tenant→patient | P8 dual portal users; cross-context 404 |
| Audit isolation | `audit.append` tenant-pinned hash-chained rows; tenant read requires `audit.read` | P8: A admin reads own audit, B audit 404; audit carries IDs only |
| Tenant switching | multi-membership user selects via `X-Tenant`; missing/foreign selector 403 | P8 dual-membership user reads both tenants; `test_tenant_isolation.py::test_multi_membership_requires_selection` |
| Branding separation (negative) | No branding module exists — tenant reads return independent names; no cross-tenant branding field exists to leak | P8: A/B tenant names independent; gap recorded below |

## 3. Gaps — missing onboarding capabilities (identified, not built)

1. No bootstrap tooling: provisioning today is test helpers
   (`tests/helpers.py::provision_tenant/provision_clinical`), not an operator
   runbook or admin API flow. Missing: documented operator checklist (provided
   below as the repeatable process), slug/name conventions, and a pre-flight
   verification script.
2. No branding storage/resolution: `branding.manage` permission exists,
   DESIGN.md §17 constrains overrides to `--hos-brand-*`, but no table,
   endpoint, or resolver exists. Pilot expectation: platform default branding
   for both tenants until P8.2.
3. No notification delivery: `NOTIFY_PROVIDER=none` in preview/production
   (fail-closed). Recalls exist but reminders do not. Pilot expectation:
   manual recall follow-up until P8.1.
4. No subscription/license enforcement: stubs only. Pilot expectation:
   single-location, manual entitlement until P8.3.
5. No patient dedup/merge, no demographics beyond name/phone, no insurances.
6. No recall board, consent list, receipt list, or audit-facet APIs
   (DESIGN.md §22 open decisions).
7. Portal document downloads honestly unavailable (`download_available=false`).
8. No optical/inventory retail, no device integration (eye pilot — see discovery).

## 4. Risks

- R1 (clinical safety): dental catalog coverage + primary dentition rejection
  unvalidated — could block pediatric cases at Pilot A. Mitigation: catalog
  review before any live use (dental discovery §2–3).
- R2 (expectation): ophthalmology has no module — Pilot B is discovery-only.
  Any promise of eye-specific screens before domain approval is a scope breach.
- R3 (operations): no bootstrap automation — manual provisioning errors
  (wrong tenant selected, unverified practitioner) are the likeliest pilot
  failure. Mitigation: follow the checklist verbatim; verify each step.
- R4 (privacy): dual-membership users (e.g. a doctor covering both clinics)
  must select tenants explicitly; missing selector fails closed (403) by design —
  train staff that this is expected, not a bug.
- R5 (branding): tenants share platform skin in this slice; do not promise
  logos/custom domains yet.

## 5. Repeatable onboarding checklist (synthetic / staging only)

For each pilot tenant, in order. Stop on any failure; never proceed past a
red step. All actions via provider API with `X-Tenant` set to the tenant
being onboarded.

- [ ] 1. Create tenant: unique slug (`pilot-dental-a`, `pilot-eye-b` style),
      display name = clinic display name. Verify: read-back shows own row only.
- [ ] 2. Create location(s): `Main Clinic` (+ `Annex` if multi-room).
      Verify: list shows only own locations.
- [ ] 3. Create tenant_admin membership (primary). Verify: admin reads tenant 200.
- [ ] 4. Register practitioner + approve verification for the doctor.
      Verify: unverified practitioner cannot author encounters (expect 403).
- [ ] 5. Create doctor membership (doctor role). Verify: doctor opens encounter 200.
- [ ] 6. Create receptionist/staff memberships with location scope.
      Verify: out-of-scope location write 403; foreign tenant read 404.
- [ ] 7. Register one synthetic patient. Verify: cross-tenant patient read 404.
- [ ] 8. Book one synthetic appointment (future start). Verify: double-book 409,
      cross-tenant read 404.
- [ ] 9. Open encounter + finalize note + record vitals + close.
      Verify: closure without note/vitals fails unless waived (422).
- [ ] 10. Dental pilot only: record finding → plan → consent → estimate →
      invoice → payment → recall (synthetic). Verify each transition code.
- [ ] 11. Enroll portal user for the synthetic patient (staff-gated).
      Verify: portal profile 200 in own context; forged ids 404; cross-tenant
      header 403/404; revocation closes access (404).
- [ ] 12. Read audit as admin. Verify: own events present with IDs only;
      other tenant's audit 404.
- [ ] 13. Dual-membership (if a user legitimately spans both): add second
      membership, verify selection required (no header → 403) and both
      selections 200.
- [ ] 14. Record tenant name/branding expectation: platform default in this slice.

Never run this checklist against production. Never use real patient data.

## 6. Recommended next slice

P8.1 notification-provider adapter (SMTP/file-relay behind `NotifyPort`,
credentials server-side, outbox/retry/DLQ preserved, consent + quiet-hour
checks added with tests) — unblocks recall reminders both pilots need — OR
P8.2 branding resolution if pilot contracts require logos first. Do not start
P8.3 (subscriptions/licensing) before one of those lands; it is the largest
scope and needs the discovery sign-offs above.
