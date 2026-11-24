# P3.0 — Workflow Acceptance Matrix

Statuses: **Pass (API)** | **Pass (UI unverified)** | **Blocked** | **Defer** | **N/A**

## Dentist pilot

### Workflow 1 — New patient

| Step | Status | Evidence |
|------|--------|----------|
| Staff login | Pass (API) / UI unverified | `auth`, `/login`; `test_auth_flow.py` |
| Open workspace | **Blocked** without operator | No `/workspaces` UI; API `POST /workspaces` OK |
| Register patient | Pass (UI unverified) | `/patients`; `test_patients_api.py` |
| Search / open profile | Pass (UI unverified) | `/patients/[id]`; `test_patient_360.py` |
| Book appointment | **Blocked** until practitioner approved | Requires `verification` approved; `scheduling/service.py` |
| Calendar + reception | Pass after approve | `/schedule`, `/reception`; `test_reception_queue.py` |

### Workflow 2 — Returning patient

| Step | Status | Evidence |
|------|--------|----------|
| Search history | Pass (UI unverified) | Timeline API + UI tabs |
| New appointment + encounter | Pass (API) | `test_clinical_api.py` |
| Complete encounter | Pass (API) | Finalize note + close |

### Workflow 3 — Dental treatment

| Step | Status | Evidence |
|------|--------|----------|
| Notes / diagnosis | Pass (API) | `encounters.py` |
| Dental chart | Pass (UI unverified) | Odontogram on encounter page; `test_dental_api.py` |
| Treatment plan | Pass (UI unverified) | `/dental/plans` |
| Estimate + payment | Pass (API) | Clinic billing suites — **not** SaaS payments |
| Timeline reflects actions | Pass (API) | `test_patient_360.py` |
| X-ray acquisition | **Defer** | Explicitly out of scope |

### Workflow 4 — Reception

| Step | Status | Evidence |
|------|--------|----------|
| Walk-in | Pass (API) | `test_reception_queue.py::test_walk_in_*` |
| Check-in + unique token | Pass (API) | Fixed check-in-day sequence (P3.0) |
| Waiting board | Pass (API) | Merges `queue_date` + start window |
| Cancel / no-show | Pass (API) | Status transitions |

### Workflow 5 — Follow-up

| Step | Status | Evidence |
|------|--------|----------|
| Create / due / overdue | Pass (UI unverified) | `/follow-ups`; `test_followups_comms.py` |
| Consent + WhatsApp link | Pass (API) | No automated WhatsApp send (correct) |

### Workflow 6 — Patient portal

| Step | Status | Evidence |
|------|--------|----------|
| Enroll synthetic patient | **Blocked** in UI | API `POST .../portal-links` only |
| Auth + isolation | Pass (API) | `test_portal_security.py` |
| Book / cancel | Pass (API) | `test_portal_booking.py` |
| Reschedule | **Defer** | Portal has cancel only |
| Document download | **Defer** | Metadata only |

### Workflow 7 — Clinic operations

| Step | Status | Evidence |
|------|--------|----------|
| Staff + roles | Pass (API); invite accept UI missing | `test_staff.py` |
| Availability | Partial | API OK; staff schedule lacks slot picker |
| Inventory + movements | Pass (UI unverified) | `test_inventory.py` |
| Ops dashboard | Pass | `test_operations_dashboard.py` + Vitest |

## Eye specialist pilot (generic clinic)

| Area | Status | Notes |
|------|--------|-------|
| Patient CRM | Pass (UI unverified) | Same as dentist |
| Appointments / reception | Same blockers as dentist (provision + approve) | |
| Generic encounter / Rx | Pass (API) | No ophthalmology fields |
| Estimates / billing | Pass (API) | Clinic AR only |
| Follow-ups / portal | Same as dentist | |
| Ophthalmology module | **N/A — discovery only** | `docs/specialties/ophthalmology-discovery.md` if present; no clinical code |

## Capability classification summary (A–G)

| Area | Classification |
|------|----------------|
| A Onboarding | Partially implemented (API strong, UI missing) |
| B Patient CRM | Implemented but insufficiently verified (UI) |
| C Appointments / reception | Implemented and verified (API); UI lightly verified |
| D Clinical | Implemented and verified (API); dental UI unverified E2E |
| E Clinic billing | Implemented and verified (API) |
| F Operations | Implemented and verified (API); reports Missing |
| G Portal | Partially implemented (security strong; enroll/download gaps) |
