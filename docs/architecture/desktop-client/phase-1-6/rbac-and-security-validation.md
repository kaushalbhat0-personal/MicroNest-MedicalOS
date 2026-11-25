# RBAC and Security Validation — M7

## Permissions used

| Capability | Permission |
|------------|------------|
| Consult nav / board | `encounter.read` |
| Open encounter | `encounter.open` |
| Close | `encounter.close` |
| Notes / dx / vitals | `clinical.create` / `clinical.read` |
| Rx | `prescription.create` / `prescription.sign` / `prescription.read` |
| Plans | `plan.manage` / `dental.read` |
| Follow-ups | `followup.manage` / `followup.read` |

## Clinical safety controls

1. Writes use `encounter.patient_id` from server-loaded encounter — not a free-typed patient override.
2. Appointment → open uses appointment.patient_id; mismatch with manual selection blocked.
3. Closed encounters: UI disables writes (backend may still accept some writes — UI fail-closed).
4. Notes/Rx require **linked practitioner** for the signed-in user (`practitioner_for_user`); otherwise 403.
5. Cross-tenant encounter access blocked (evidence).
6. No PHI in evidence JSON or console logging of clinical content.
7. `encounterViewId` + patient view cleared on logout / clinic switch.

## Client role distrust

Doctor dashboard variant is UX only. Missing permissions hide write controls; API still enforces.
