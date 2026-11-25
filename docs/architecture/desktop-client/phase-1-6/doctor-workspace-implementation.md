# Doctor Workspace Implementation

## Screens

| Screen | Route | Component |
|--------|-------|-----------|
| Consult board | `/encounters` | `DoctorConsultBoard` |
| Encounter workspace | `/encounters/{id}` | `EncounterWorkspace` |

## Entry points

- Consultations nav (`encounter.read`)
- Appointment details → Open consultation
- Reception queue → Consult
- Patient 360 → Open consultation
- Query: `?appointment=&patient=` with wrong-patient guard on open

## Board features

- Today's appointments (non-terminal)
- Waiting / checked-in queue slice
- Open encounters list + Resume
- Manual open (patient search) with optional chief complaint
- Location + approved practitioner filters
- Opens encounter with `appointment_id` when started from appointment (patient id taken from appointment only)

## Workspace features

- Patient identity header (always from encounter.patient_id)
- Context: demographics, overview, recent timeline titles
- Tabs: notes, vitals, diagnoses, rx, plans, follow-up
- Close encounter with ConfirmDialog + optional waivers
- Closed = UI write lock
- Dirty-note warning on back navigation
- Clinical UI state cleared on workspace switch / logout (`encounterViewId`)

## Client modules

- `apps/desktop/src/lib/clinicalApi.ts`
- `apps/desktop/src/components/clinical/*`
