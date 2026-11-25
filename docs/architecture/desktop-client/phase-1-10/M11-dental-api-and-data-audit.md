# M11 Dental API and Data Audit

**Branch:** `release/p3-7b-staging` @ `293dc66`  
**Date:** 2026-11-25  
**Clinical validation:** **PENDING** (no dentist sign-off this milestone)

## Capability matrix

| Workflow | Backend support | Desktop (pre-M11) | Desktop (M11) | Security | Clinical validation | Decision |
|----------|-----------------|-------------------|---------------|----------|---------------------|----------|
| FDI permanent teeth | `validate_tooth` 11–48 | Partial (free number input) | Odontogram + validation | Tenant + practitioner | Implemented, not dentist-signed | **SUPPORTED** |
| Primary dentition 51–85 | Deferred | — | Documented deferred | — | Requires dentist decision | **NOT_IMPLEMENTED** |
| Tooth findings + surfaces | Full API | Missing | Dental tab | `dental.record` | Catalog conditions | **SUPPORTED** |
| Odontogram storage | None (UI projection) | Missing | UI projection only | N/A | Per P3-02 | **SUPPORTED** |
| Condition catalog | GET conditions | Missing | Select from catalog | `dental.read` | Seeded codes | **SUPPORTED** |
| Treatment plan draft | POST plans | Draft create only | Hub + encounter | `plan.manage` | — | **SUPPORTED** |
| Plan activate/complete/cancel | Full | Not wired | Hub + Plans tab | `plan.manage` | Plan consent gate **PENDING** | **SUPPORTED** (activation not consent-gated) |
| Plan item status | Full | Missing | Hub | `plan.manage` | — | **SUPPORTED** |
| Procedure records | Full | Missing | Dental tab | `dental.record` | Consent gate PASS (P3.6) | **SUPPORTED** |
| Clinical consent create/decide/withdraw | Full | Missing | Session-tracked UI | `dental.record` | Policy questions open | **PARTIALLY_SUPPORTED** (no list API) |
| List consents by plan/procedure | **MISSING** | — | Session state only | — | — | **NOT_IMPLEMENTED** |
| Consent expiry | No model | — | — | — | N/A | **NOT_IMPLEMENTED** |
| Estimate from plan | Billing estimate APIs | Read-only | Unchanged M8/M10 | `billing.*` | — | **PARTIALLY_SUPPORTED** |
| Imaging annotation | Research only | — | Out of scope | — | D2B review separate | **NOT_IMPLEMENTED** |
| AI diagnosis / CDS | None | — | Explicitly excluded | — | — | **NOT_IMPLEMENTED** |

## Entity distinctions

| Entity | Meaning |
|--------|---------|
| ToothFinding | Observed condition fact (active/resolved) |
| TreatmentPlan / Item | Clinical intent (not money) |
| DentalProcedureRecord | Planned/performed procedure instance |
| Consent | Plan XOR procedure subject |
| Estimate / Invoice | Billing layer (P4) — separate |

## Permissions

`dental.read`, `dental.record`, `plan.manage` (+ existing clinical/billing perms for linked steps).

## Source docs

- `docs/decisions/P3-02-dental-model.md`
- `docs/security/P3-6-dental-consent-report.md`
- M7 phase-1-6 treatment-plan notes
