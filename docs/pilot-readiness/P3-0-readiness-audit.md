# P3.0 — Healthcare OS Pilot Readiness Audit

**Date:** 2026-11-24  
**Baseline HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**Migration head:** `0027_saas_payment_reliability`  
**SaaS payments:** P2.5 freeze — do not expand Razorpay / P2.6 for pilots.

## 1. Executive verdict

**CONDITIONAL PASS**

The product can support **two assisted pilots** (dentist + eye specialist on generic clinic workflows) if operators follow the onboarding runbook. It is **not** self-serve clinic-ready: workspace provisioning UI, practitioner approval UI, portal enrollment UI, and production email delivery are missing. Staff browser E2E is not automated.

SaaS payment-provider work is frozen at P2.5 and is **not required** for clinic pilots (clinic AR billing remains in scope).

## 2. Git state (start of audit)

- HEAD: `2a0974e41af9e334e147794f45e258f34d6814d3`
- Dirty tree preserved (~131 paths before audit docs/fixes). No commit/push/stash/reset.

## 3. What is genuinely ready (API-verified)

| Domain | Evidence |
|--------|----------|
| Signup / verify / workspaces (API) | `signup.py`, `workspaces.py`; `test_signup_api.py`, `test_workspaces_api.py`, `test_o15r_two_pilot_e2e.py` |
| Patient CRM | `patients.py`, `/patients`; `test_patients_api.py`, `test_patient_360.py` |
| Scheduling + reception queue | `scheduling.py`, `/schedule`, `/reception`; `test_appointments_api.py`, `test_reception_queue.py` |
| Clinical + dental chart/plans | `encounters.py`, `dental.py`, odontogram UI; `test_clinical_api.py`, `test_dental_api.py` |
| Clinic billing (not SaaS) | `billing.py`, `/billing/*`; billing API/service suites |
| Follow-ups + WhatsApp link | `communications.py`, `/follow-ups`; `test_followups_comms.py` |
| Inventory / staff / ops dashboard | `inventory.py`, `staff.py`, `operations.py`; matching API tests |
| Patient portal security | `portal.py`; `test_portal_security.py`, isolation suites |
| Tenant isolation / RLS | `tests/isolation/*` |

## 4. What is not ready

| Gap | Impact |
|-----|--------|
| No workspace provision UI | Owner cannot create clinic from browser after signup |
| Owner practitioner stays `pending` | Booking UI hides non-approved practitioners |
| No invite-accept page | Second staff needs API |
| No portal-link enrollment UI | Portal users need API/script |
| Portal document download disabled | `download_available=False` |
| No portal reschedule | Cancel/book only |
| No production email/SMS provider | Verify/invite delivery blocked outside DEV_NOTIFICATIONS |
| No staff Playwright E2E | UI journeys unverified in CI |
| Ophthalmology specialty code | Discovery only — no clinical module |

## 5. Low-risk fixes applied during audit

1. **Reception queue tokens** — sequence uses location-local **check-in day**; board merges `queue_date` rows (`backend/app/modules/scheduling/service.py`). Fixes midnight-straddle duplicate token `1`.
2. **Test harness** — idempotent plan seed + wipe NULL seed roles before re-insert (`tests/conftest.py`).
3. **O1.5R assertions** — `limits.enforced` expected `True` after P2.2 (`tests/api/test_o15r_two_pilot_e2e.py`).

No SaaS payment code changed.

## 6. Companion documents

- `P3-0-workflow-matrix.md` — dentist + eye specialist acceptance matrices  
- `P3-0-security-review.md` — security / isolation  
- `P3-0-pilot-onboarding-plan.md` — assisted runbook + eye discovery checklist  
- `P3-0-gap-backlog.md` — prioritized backlog for P3.1  

## 7. Acceptance criteria to declare “pilot ready”

1. Operator runbook provisions two synthetic clinics (dental + generic/eye).  
2. Dentist workflows 1–5 pass on synthetic data (API or assisted UI).  
3. Eye specialist completes generic workflows; discovery checklist filled (no ophthalmology build).  
4. Isolation + portal security suites green on `healthcare_os_test` (serial).  
5. Reception queue uniqueness verified.  
6. Explicit deferrals signed: portal file delivery, self-serve provision UI, SaaS payments.

## 8. Recommended next phase

**P3.1 — Pilot onboarding UX & reception hardening** (not P2.6 payments): workspace create UI, practitioner approve UI, portal enroll UI, invite accept page, optional portal document download with server-bound keys.
