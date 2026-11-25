# M7 Clinical API Audit

**Branch:** `release/p3-7b-staging` @ `293dc66`  
**Date:** 2026-11-25  
**Source of truth:** FastAPI modules under `backend/app/modules/clinical`, `prescriptions`, `dental`, `billing/estimates`, `communications`.

## Encounter lifecycle

| From | To | API | Notes |
|------|-----|-----|-------|
| — | `open` | `POST /tenants/{t}/encounters` | Requires verified practitioner; optional `appointment_id` must match patient |
| `open` | `closed` | `POST .../encounters/{id}/close` | Finalized note OR `note_waiver`; vitals OR `vitals_waiver`; no draft Rx/plans |
| `closed` | — | — | Terminal |

**No PATCH encounter.** Status enum is only `open` | `closed` (no `in_progress`).

## Feature matrix

| Feature | API | Permission | Transition | Consent | Tests |
|---------|-----|------------|------------|---------|-------|
| Open encounter | POST `/encounters` | `encounter.open` | → open | commercial gate | `test_clinical_api.py` |
| List/get encounter | GET | `encounter.read` | — | location scope | same |
| Close encounter | POST `.../close` | `encounter.close` | open→closed | — | `test_clinical.py` |
| Create draft note | POST `.../clinical-notes` | `clinical.create` | → draft | ≥1 content field | `test_clinical_api.py` |
| Finalize note | POST `.../clinical-notes/{id}/finalize` | `clinical.create` | draft→finalized; author-only | — | same |
| Amend note | POST `.../amend` | `clinical.create` | new finalized + old amended | — | same |
| PATCH draft note | **MISSING** | — | Create new draft instead | — | — |
| Diagnosis create | POST `.../diagnoses` | `clinical.create` | → active | XOR code/free_text | same |
| Diagnosis codes | GET `/diagnosis-codes` | `clinical.read` | ICD10/SNOMED catalog | — | contract |
| Rx create | POST `.../prescriptions` | `prescription.create` | → draft | catalog meds | `test_rx_dental.py` |
| Rx sign | POST `.../sign` | `prescription.sign` | draft→signed; prescriber-only | — | same |
| Treatment plan create | POST `/treatment-plans` | `plan.manage` | → draft | **activate not consent-gated** | `test_dental_api.py` |
| Procedure in_progress/completed | POST procedure status | `dental.record` | RECORD_TRANSITIONS | **granted consent required** | `test_p36_*` |
| Estimates | CRUD under `/estimates` | `billing.*` | draft→issued→… | no clinical consent | `test_billing_estimates_api.py` |
| Follow-ups | POST/GET `/follow-ups` | `followup.manage/read` | open↔… | — | `test_followups_comms.py` |
| Timeline clinical | GET patient timeline | `patient.read` | encounters, rx, plans | notes/vitals/estimates **omitted** | `test_patient_360.py` |

## Ambiguous / unsupported (do not invent)

1. No draft-note in-place edit — UI creates new drafts or uses amend after finalize.
2. Closed encounters: UI treats as read-only; backend may still accept some writes — desktop blocks writes when `status === "closed"`.
3. Plan activate without dental consent is **existing backend policy** — not changed; procedure-level consent still enforced.
4. No AI diagnosis/Rx; no dose calculation; no auto WhatsApp.
5. `practitioner_id` on plan create schema ignored by API (uses linked practitioner).

## Desktop entry points

- `/encounters` — consult board  
- `/encounters/{id}` — workspace  
- Query: `?appointment=&patient=` from calendar/queue/360
