# Clinic ERP + Patient Portal — Gap Audit

**Date:** 2026-11-24  
**Checkpoint audited:** `2a0974e41af9e334e147794f45e258f34d6814d3` (`main` / `origin/main`)  
**Method:** Code, migrations, API contracts, UI routes, and pytest evidence — not route existence alone.

## Verdict

Healthcare OS already has a strong **modular monolith** foundation: tenancy/authz, P2 scheduling, P3 clinical/dental, P4 billing, and P6 patient portal self-read with solid isolation tests.

It is **not yet a complete clinic ERP CRM**. The pilot clinic cannot fully replace an Excel patient register, cannot offer patient self-booking, and the patient workspace is a tabbed aggregation — not a chronological longitudinal record.

## Documents

| # | File | Focus |
|---|------|--------|
| 01 | `01-current-platform-inventory.md` | What exists by module |
| 02 | `02-patient-crm-gaps.md` | Patient identity / CRM |
| 03 | `03-appointment-workflow-gaps.md` | Scheduling / reception |
| 04 | `04-patient-profile-and-history.md` | Unified patient workspace |
| 05 | `05-patient-portal-gaps.md` | Portal self-service |
| 06 | `06-billing-and-followups.md` | Finance + recalls/comms |
| 07 | `07-inventory-and-staff.md` | Inventory stub + staff |
| 08 | `08-multi-specialty-readiness.md` | Specialty packs |
| 09 | `09-security-and-privacy-review.md` | Authz / release / isolation |
| 10 | `10-prioritized-roadmap.md` | P0–P3 |
| 11 | `11-pilot-clinic-acceptance-criteria.md` | Pilot gates |
| 12 | `12-implementation-slice-plan.md` | Selected vertical slice |

## Classification legend

- **IMPLEMENTED AND VERIFIED** — code + tests (or equivalent isolation proof)
- **IMPLEMENTED BUT NEEDS IMPROVEMENT** — works; UX/coverage/product gaps remain
- **PARTIALLY IMPLEMENTED** — incomplete surface or projection
- **MISSING** — no usable implementation
- **BLOCKED BY EXTERNAL DECISION** — needs clinical/legal/product sign-off
- **OUT OF SCOPE** — explicitly deferred for this phase/product rule

## Selected first implementation slice

**Patient CRM foundation → staff appointment reuse → portal availability + booking → patient profile appointments/history enrichment.**

See `12-implementation-slice-plan.md`.

## Non-goals (enforced)

- No D2 dental image annotation schemas/UI
- No ophthalmology clinical workflows
- No automated WhatsApp Business sending
- No second patient/appointment/portal subsystem
- No rebuild of P2/P3/P4/P6 modules that already work
