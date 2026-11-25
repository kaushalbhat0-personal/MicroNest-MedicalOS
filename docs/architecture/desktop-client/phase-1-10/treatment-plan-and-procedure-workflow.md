# Treatment Plan and Procedure Workflow

## Treatment plans

| Status | Desktop |
|--------|---------|
| draft | Create in encounter Plans tab or TreatmentPlansHub; add items while draft |
| active | Activate via hub/Plans (ConfirmDialog); **not consent-gated** (P3.6) |
| completed | When items terminal |
| cancelled | Cascades open items |

Distinctions shown from backend status fields: proposed / planned / in_progress / completed / cancelled on items.

Plan ≠ estimate ≠ invoice — captions in UI.

## Procedure records

| Status | Consent |
|--------|---------|
| planned | Not required |
| in_progress | **Granted consent required** (403 otherwise) |
| completed | **Granted consent still required** |
| cancelled | No consent required |

Desktop: create planned record; before gated transitions, session consent create+grant; backend remains authority.

## Consent list gap

No `GET /consents` — UI keeps consents created in the current session. Refresh loses local list (records remain server-side). Documented **NOT_IMPLEMENTED**.

## Estimate linkage

Estimates remain billing-owned (M8). Plans may link via estimate `treatment_plan_id` where billing supports it; M11 does not invent auto-invoice from plans.
