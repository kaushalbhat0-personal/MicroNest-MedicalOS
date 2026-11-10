# 07 — Prioritized backlog (dental-erp @ 389d9841)

Scored on: clinical workflow value, patient safety, dentist usability, chair-time
saved, patient experience, UI/UX gain, reuse simplicity, architectural fit,
maintenance burden, license clarity. AI-poweredness counted for nothing (§12).

## Must-have (do first; all adapted/recreated, none verbatim)

1. **Imaging viewer** (RC-1, class B) — fills a wholly missing module; every
   other imaging item depends on it. Needs storage signed-URL plumbing first.
2. **Image annotation** (RC-2, class B) — same justification; normalized coords,
   undo/redo, read-only, UUID ids, tenant-scoped persistence.
3. **Odontogram surface-select + legend + working history + read-only + responsive**
   (RC-4, class C) — core dentist instrument; our model already supports it.

## High-value (next)

4. **Before/after compare** (RC-3, class B) — cheap once the viewer exists.
5. **Patient-workspace documents/imaging section + lazy timeline** (RC-5, class B/C)
   — organization over existing rows; no new entities.
6. **Plan progress + consent badges + grouped procedure picker** (RC-6, class D
   ideas) — presentation-only, server values.
7. **Global-search micro-pattern + notification-tray micro-pattern** (RC-7/8,
   class B) — small, shared-shell wins once scoped APIs exist.

## Later (reference only; separate scoping)

8. Recall reminders via notification provider (P8.1) + recall→booking UX.
9. Lab-orders module (work-type/status taxonomy from their implementation).
10. Dentist-facing recall board / consent list / plan-progress aggregates (§22 APIs).
11. Consent signature-reference + text versioning (P-D) + rendering pipeline.
12. Timeline projection across encounters/plans/records.
13. Sterilization / inventory-alert concepts (post-scope modules).
14. Primary dentition (dentist scope decision P-B first — potential blocker).
15. Catalog-review session outcomes (P-A) + surface-rule ruling.

## Reject / defer

- **Reject now:** all backend/API/Prisma/MySQL/tenancy/auth/billing/payments/AI/
  portal-server code (RC-10); client money math; free-text teeth; PHI-in-URL
  habits; no-op Print; tile-wall dashboard aesthetic; their icon/brand.
- **Defer:** video consults, chat widget, insurance pre-auth, payment plans,
  marketing/CRM/surveys — out of Dental-specialty scope.
- **Do not prioritize:** any AI skill merely because advertised (16 skills, 16
  routes — rejected wholesale with rationale in `04`/`06`).
