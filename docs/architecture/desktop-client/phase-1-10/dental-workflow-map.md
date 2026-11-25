# Dental Workflow Map (Supported)

```
Patient → Encounter (open)
  → Tooth findings (FDI + surfaces + condition catalog)
  → Diagnosis (generic clinical — separate from findings)
  → Treatment plan (draft → active → completed|cancelled)
  → Plan items (proposed → planned → in_progress → completed|cancelled)
  → Procedure record (planned → in_progress → completed|cancelled)
  → Consent (procedure subject; granted required for in_progress/completed)
  → Estimate / Invoice / Payment (billing modules — not dental money fields)
```

## Transition table

| Step | Source | API | Permission | Validation | Audit | Reversible | Dentist approval |
|------|--------|-----|------------|------------|-------|------------|------------------|
| Record finding | Encounter | POST `.../tooth-findings` | `dental.record` | FDI permanent; surfaces set; open encounter; verified practitioner | `finding.recorded` | Resolve only (history kept) | Catalog semantics PENDING |
| Resolve finding | Finding | POST resolve | `dental.record` | active → resolved | `finding.resolved` | No un-resolve | — |
| Create plan | Patient | POST `/treatment-plans` | `plan.manage` | Items optional at create; catalog procedures | `plan.created` | Cancel | — |
| Activate plan | Plan | POST activate | `plan.manage` | ≥1 item; draft | `plan.activated` | Cancel | **Consent gate PENDING** (not enforced) |
| Complete/cancel plan | Plan | POST complete/cancel | `plan.manage` | Service rules | plan.* | Terminal | — |
| Plan item status | Item | POST status | `plan.manage` | Transition table | `plan.item_status` | Limited | — |
| Procedure record | Encounter | POST procedure-records | `dental.record` | Catalog code; FDI | `procedure.recorded` | Cancel | — |
| Procedure → in_progress/completed | Record | POST status | `dental.record` | **Granted consent on record** | `procedure.status` | Cancel without consent | P3.6 policy PENDING sign-off |
| Consent decide | Consent | POST decide | `dental.record` | pending only | `consent.decided` | Withdraw from granted | — |
| Estimate/invoice | Billing | M8/M10 APIs | billing.* | Separate layer | billing audits | Per billing | — |

Unsupported forced transitions are not exposed in desktop.
