# 05 — Patient portal gaps (P6 / P6.1)

Authority: `api/v1/portal.py`, `modules/portal/`, `apps/web/app/portal/**`, `tests/portal/**`.

## Release vocabulary (enforced in code)

| Layer | Meaning |
|-------|---------|
| Record exists | DB row may be draft/open |
| Finalized / issued | Note finalized/amended; Rx signed; invoice/estimate not draft |
| Eligible for portal | Projection rules in `portal.py` |
| Visible to patient | Returned on `/api/v1/portal/*` for linked patient |

**Never equate** `DENTAL_READ` / provider perms with portal visibility.

## Matrix

| Capability | Classification | Evidence |
|------------|----------------|----------|
| Auth + sessions | **IMPLEMENTED AND VERIFIED** | Shared identity cookies; portal 401 after logout |
| Portal link binding | **IMPLEMENTED AND VERIFIED** | `portal_links`; server-derived `patient_id` |
| Multi-clinic access | **IMPLEMENTED BUT NEEDS IMPROVEMENT** | Multiple links possible; workspace routing flags; weak selector UX |
| Profile read | **IMPLEMENTED BUT NEEDS IMPROVEMENT** | Name/phone only |
| Appointments list/detail | **IMPLEMENTED AND VERIFIED** | `/portal/appointments` |
| Cancel appointment | **IMPLEMENTED AND VERIFIED** | `PORTAL_APPOINTMENT_CANCEL`; scheduled/confirmed only |
| Book appointment | **MISSING** | No create; UI: “contact the clinic” |
| Reschedule (patient) | **MISSING** | — |
| Availability for self-book | **MISSING** | — |
| Closed visit summaries | **IMPLEMENTED AND VERIFIED** | Closed enc + finalized notes; drafts hidden (`test_portal_security.py`) |
| Prescriptions | **IMPLEMENTED AND VERIFIED** | Signed/cancelled only |
| Treatment plans | **IMPLEMENTED BUT NEEDS IMPROVEMENT** | Draft plans currently listed (permissive) |
| Documents | **PARTIALLY IMPLEMENTED** | Metadata; `download_available=false` |
| Billing / payments / receipts | **IMPLEMENTED AND VERIFIED** | Drafts filtered; display-only money |
| Online pay | **MISSING** | Explicit UI deferral |
| Portal notifications inbox | **MISSING** | — |
| Notification consent UI | **MISSING** | Eligibility module only |
| Account recovery | **IMPLEMENTED AND VERIFIED** | Existing password-reset flow used for new portal users |
| Cross-patient / tenant isolation | **IMPLEMENTED AND VERIFIED** | Security + RLS + two-tenant suites |
| Access log | **IMPLEMENTED AND VERIFIED** | Own `portal_user` audits |
| Separate `apps/patient-portal` app | **OUT OF SCOPE** (v1) | Keep `/portal` in `apps/web` |

## Critical product gap

Portal is a **strong read + cancel** surface. Pilot retention needs **self-booking** on the same appointment model with concurrency safety and no PHI leakage in availability responses.

## Post-slice note

Self-booking + portal-safe availability (`GET /portal/availability`, `POST /portal/appointments`, `portal.appointment.book`) and bookable location/practitioner lists are in the first vertical slice. Still open: patient reschedule, online pay, document download, notification consent UI, stricter draft treatment-plan filtering.