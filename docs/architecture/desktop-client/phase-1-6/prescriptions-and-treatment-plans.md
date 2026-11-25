# Prescriptions and Treatment Plans

## Prescriptions

| Action | API | Permission | Policy |
|--------|-----|------------|--------|
| Catalog | GET `/medications` | `prescription.read` | No invented drug list |
| Create draft | POST `.../prescriptions` | `prescription.create` | Linked practitioner required |
| Sign | POST `.../prescriptions/{id}/sign` | `prescription.sign` | Prescriber-only; draft→signed |
| Cancel/correct | existing endpoints | sign/create | Not primary M7 desktop flows |

Desktop: medication search (local filter), dose/route/frequency/duration/instructions, review step, then create; Sign when permitted. **No dose calculation or clinical recommendations.**

Draft Rx blocks encounter close until signed or otherwise cleared.

## Treatment plans

| Action | API | Permission | Policy |
|--------|-----|------------|--------|
| Create draft | POST `/treatment-plans` | `plan.manage` | Schema requires `practitioner_id`; catalog procedure codes (e.g. `cleaning`, `filling`) |
| Activate | POST activate | `plan.manage` | **Not wired in M7 desktop** (limitation) |
| Procedure in_progress/completed | procedure status | `dental.record` | **Granted dental consent required** |

Desktop: create draft plan only; list existing plans; list estimates read-only. Does not auto-invoice or auto-activate.

## Estimates

Read-only list via `GET /estimates?patient_id=` when `billing.read` allows. No issue/convert UI in M7.
