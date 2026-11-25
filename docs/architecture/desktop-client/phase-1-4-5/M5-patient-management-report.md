# M5 — Patient Management Report

**Verdict: PASS**

## Implemented

| Feature | Desktop surface | Notes |
|---------|-----------------|-------|
| M5.1 Directory | `PatientsDirectory` | Search (`q`), active filter, client page of server limit≤100 |
| M5.2 Registration | Same page form | Fields match `PatientCreateRequest`; opens profile after create; soft duplicate warning |
| M5.3 Profile 360 | `PatientProfile` | Identity header, overview cards, tabs for demographics/history/appointments/clinical/billing/care |
| M5.4 Editing | Demographics tab PATCH | Requires `patient.update`; deactivate via ConfirmDialog |
| M5.5 History | Timeline tab | Backend order + category filter + cursor pagination; events not silently dropped |
| M5.6 Workflow | Receptionist + doctor | Nav gated by `patient.read`; restricted sections omitted on 403 |

## Authorization

- List/get/overview/timeline → `patient.read`
- Create → `patient.create`
- Patch → `patient.update`
- Hidden nav is not authz; API returns 403 and UI shows error / omits section

## Out of scope (deferred)

Clinical note/prescription/plan editors, billing screens, document upload UI (read-only lists when authorized).

## Blockers

None for M5 acceptance. Registration date / last-visit columns on directory use overview only after open (list API does not return last visit).
