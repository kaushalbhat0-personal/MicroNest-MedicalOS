# 04 — Patient profile and unified history

## Current surface

`apps/web/app/patients/[id]/page.tsx` — tabbed workspace:

- Overview (contact + counts)
- Encounters (list → deep link)
- Dental (plans + recalls)
- Billing (invoices + payments + credit)

Clinical depth lives on `encounters/[id]`. Money detail on billing routes.

## Matrix

| History element | Classification | Evidence |
|-----------------|----------------|----------|
| Registration identity | **PARTIALLY IMPLEMENTED** | Name/phone/`is_active` only |
| Appointments on profile | **IMPLEMENTED BUT NEEDS IMPROVEMENT** (post-slice) | Appointments tab + edit/WhatsApp on overview; still not a chronological cross-domain feed |
| Encounters | **IMPLEMENTED BUT NEEDS IMPROVEMENT** | List only; no notes/vitals summary here |
| Clinical notes / vitals / diagnoses | **PARTIALLY IMPLEMENTED** | On encounter page, not profile timeline |
| Prescriptions on profile | **MISSING** | Encounter-scoped API only in staff UI |
| Treatment plans / recalls | **IMPLEMENTED AND VERIFIED** | Dental tab |
| Estimates | **MISSING** on profile | Exist under `/billing/estimates` |
| Invoices / payments / dues | **IMPLEMENTED BUT NEEDS IMPROVEMENT** | Parallel tables, not chronological |
| Documents | **MISSING** on profile | Encounter DocsTab / dental refs |
| Follow-ups | **PARTIALLY IMPLEMENTED** | Recalls only |
| Communications | **MISSING** | No log; WhatsApp handoff absent |
| Chronological unified feed | **MISSING** | No server aggregation/read model |
| Duplicate timeline DB | **OUT OF SCOPE** | Prefer read aggregation over copy |

## Design preference

Server-side **read aggregation** with authz + pagination (appointments, encounters, billing events) — never duplicate clinical/billing rows into a second history store.
