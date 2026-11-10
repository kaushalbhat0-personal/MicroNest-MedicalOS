# Dental pilot workflow discovery — Nevase's Multispeciality Dental Clinic (Pilot A)

Status: discovery (no dentist approval claimed). Synthetic data only.
Scope: validate the existing Dental module against a practical single-clinic
workflow. No schema changes in this slice. No clinical rules invented.

Code basis: `backend/app/modules/dental/service.py`, `backend/app/modules/dental/plans.py`,
`backend/app/api/v1/dental.py`, `backend/app/modules/clinical/service.py`,
`backend/app/modules/clinical/records.py`, `backend/app/modules/billing/*`,
`backend/app/api/v1/portal.py` (portal projections).

## 1. Workflow map (step → code → state)

| # | Step | Existing implementation | Portal visibility |
|---|---|---|---|
| 1 | Reception + patient registration | `patients.register_patient` — display_name (2–200), optional phone ≤32. Tenant-scoped; cross-tenant reads 404. No dedup, no demographics, no insurance. | Profile header only (`portal/profile`: id, display_name, phone, is_active). |
| 2 | Appointment | `scheduling.create_appointment` — future-start, 5–480 min, advisory-lock double-book guard, idempotency key, location scope, practitioner must be verified in tenant. Lifecycle scheduled→confirmed→checked-in→completed/cancelled/no-show. | List + detail + cancel (scheduled/confirmed only). |
| 3 | Encounter open | `clinical.open_encounter` — patient/practitioner/location/appointment scope checks. | Header only while open. |
| 4 | Patient history / examination note | `records.create_note` (SOAP-ish free text) → `finalize_note` (author-only) → `amend_note` (supersede chain, old row kept). Closure requires finalized note or explicit waiver. | Closed encounters: finalized/amended notes only. Drafts never projected. |
| 5 | Vitals/observations | `records.record_observation` — typed catalog (`observation_types`), range-checked, immutable + correction chain. Closure requires vitals or waiver. | All observations on closed encounters (no recorded_by leak). |
| 6 | Odontogram | Frontend projection only (`packages/ui/dental.tsx`, DESIGN.md §14): SVG over finding rows. No stored pixels. FDI permanent 11–48 (`dental.service.PERMANENT_TEETH`); primary 51–85 rejected. 8 surfaces, lowercased, deduped, unique per finding. | Not directly projected; plans/recalls/consents are. Odontogram itself is provider-side. |
| 7 | Tooth/surface findings | `dental.record_finding` + `resolve_finding` (active→resolved only). Condition must be active catalog row. Surfaces normalized rows with `uq_finding_surface`. | Not projected as findings; surfaced via plans/records. |
| 8 | Diagnosis | `records.add_diagnosis` — coded XOR free-text, supersede chain, resolve to resolved/ruled_out. | Active/resolved diagnoses on closed encounters. |
| 9 | Treatment plan | `plans.create_plan` (draft) → add items (draft-only) → `activate_plan` (needs ≥1 item) → item transitions proposed→planned→in_progress→completed/cancelled → `complete_plan` (all items terminal) / `cancel_plan`. Plan is clinical, never money. Encounter-linked plans block encounter closure while draft. | Full plan list + detail (items with procedure code/display, tooth, surface, status). |
| 10 | Procedure record | `plans.record_procedure` (planned) → in_progress → completed/cancelled. Optional link to plan item (referential only, no auto state-sync). | Not directly listed in portal; consents referencing records are. |
| 11 | Consent | `plans.create_consent` — exactly one subject (plan XOR record, DB check), consenter_name 2–200, decide granted/declined (once), withdraw (granted→withdrawn). `document_ref` is a string pointer only. | Status + consenter name/relation + decided_at (no document bytes). |
| 12 | Estimate | Billing estimates: draft → issued snapshot, line-level convert to invoice, idempotency keys, FY doc numbers. | Issued+ only; drafts hidden. |
| 13 | Invoice | Draft → issued (frozen, numbered) → void (reason required). Money as server strings. | Issued+ only; same freeze semantics. |
| 14 | Payment + receipt/refund | Payments with allocation, receipts, refunds, credit notes; all idempotent per tenant. | Payments, receipts, refunds, credit notes, credit balance (display-only). |
| 15 | Recall / follow-up | `plans.create_recall` — patient + location + due_date + reason 2–200, practitioner optional but must be verified if given. Transitions scheduled→completed/cancelled/missed (one-way out of scheduled). No campaign engine, no automation. | Recall list (due_date, reason, status, location_id). |
| 16 | Documents/imaging | `plans.create_document_ref` — metadata pointer (doc_type ∈ xray/scan/photo/report/other, storage_key required). Bytes behind StoragePort; portal gets metadata only, `download_available=false`. | Metadata on closed encounters only; storage keys never leave server. |

## 2. Verdicts per item

### Existing and verified (tests + code)

- Tenant-scoped CRUD on every dental row; cross-tenant reads/writes 404
  (`tests/isolation/test_clinical_isolation.py`, `tests/api/test_dental_api.py`).
- Finding lifecycle, plan lifecycle, record lifecycle, consent single-subject
  check, recall one-way transition — all service-enforced with conflict/validation errors.
- Encounter closure ceremony (note-or-waiver, vitals-or-waiver, draft Rx/plan blockers).
- Audit carries opaque IDs only (dental PHI probe test).
- Portal release rules (drafts hidden, closed-only clinical, metadata-only docs).

### Existing but NOT validated clinically (requires dentist approval)

1. Condition catalog coverage — are the seeded `dental_conditions` codes sufficient
   for caries/periodontal/endo/ortho/surgical presentations seen at this clinic?
2. Procedure catalog coverage — does `dental_procedures` cover the clinic's actual
   service mix (restorative, endo, perio, prostho, surgical, preventive)?
3. Surface model — 8-surface set with no anterior/posterior appropriateness rule
   (documented deferral in `dental/service.py`). Is `incisal` vs `occlusal` vs
   `palatal` handling acceptable chair-side?
4. Primary/mixed dentition — hard-rejected (51–85). Clinic sees children?
   If yes, this is a blocker, not a nit.
5. Finding→plan→record linkage is referential, not workflow-driven: recording a
   procedure does not advance the plan item; completing items does not complete
   the record. Is manual dual-tracking acceptable or error-prone?
6. Consent model — single subject, string `document_ref`, no signature capture,
   no versioning of consent text, no vernacular-language support. Legally sufficient?
7. Recall model — review dates only, no reminders/notifications (provider=P8.1 gap),
   no chair-time linkage. Does the clinic need recall → appointment booking?
8. Estimate↔plan linkage — plans and estimates are separate objects with no
   system link (plan item → estimate line is manual). Acceptable for informed
   financial consent?
9. Multi-location — location scope exists, but plan-without-encounter rows are
   invisible to location-scoped users by design. Correct for this clinic?
10. Odontogram UX — projection correctness, keyboard roving grid, surface select,
    and tablet chair-side behavior need dentist walkthrough (no clinical test exists).

### Missing (no code)

- Patient dedup / merge, demographics depth, insurance/uplink fields.
- Pediatric dentition, perio charting, endo charting specifics.
- Chair/room/queue operations beyond locations.
- Consent signature capture + document rendering pipeline (print/PDF open decision,
  DESIGN.md §22).
- Recall reminders (blocked on real notification provider).
- Dentist-facing recall board / consent list / receipt list APIs (DESIGN.md §22 open).
- Imaging viewer beyond metadata pointers.

### Proposed (no commitment; dentist decides)

- P-A: seed-catalog review session — dentist marks keep/add/rename on conditions
  and procedures; changes land as data migration + test, never inline edits.
- P-B: decide primary-dentition scope before any schema work.
- P-C: decide whether plan-item ↔ procedure-record should auto-link or stay manual
  (safety trade-off: automation hides clinician intent).
- P-D: consent text versioning + signature reference design (storage-backed).
- P-E: recall → appointment booking UX (reception flow, not auto-booking).

## 3. What must the dentist confirm (checklist for the visit)

- [ ] Daily patient mix (adult/child ratio) — determines primary-dentition priority.
- [ ] Condition + procedure catalog walkthrough (project the two lists on screen).
- [ ] Finding → plan → consent → estimate → invoice → payment on one real-style
      case (synthetic patient), narrated by the dentist.
- [ ] Odontogram chair-side test (tablet if used).
- [ ] Recall workflow: who follows up, how, and what "missed" means.
- [ ] Consent practice: paper today? What must the software capture to replace it?
- [ ] Billing practice: estimates always? Part-payments? Refunds/credit notes?
- [ ] Portal expectations: what should patients see (plans, recalls, invoices)?

No workflow is approved until this walkthrough happens.
