# 04 — Functional gap analysis (DentalERP → our OS → gap → enhancement)

Format: DentalERP capability → our existing capability → actual gap → proposed
enhancement. "Missing" is only claimed after checking our tree (evidence paths
included). Classifications (A–E) are defined in `06-reuse-candidates.md`.

## 1. Dental charting / odontogram

- **Theirs:** two SVG charts (fetch-driven 611-line + legacy prop-driven 523-line),
  32 permanent teeth, 14-condition enum, 5-surface booleans, severity, dialog
  editing, summary counts, tooltip, dead history list, no read-only, no keyboard grid.
- **Ours:** `packages/ui/dental.tsx` (SVG projection, roving tabindex,
  4 states via tokens), `backend/app/modules/dental/service.py` (findings +
  8 surfaces + active→resolved), encounter Dental tab with record/resolve,
  `tests/api/test_dental_api.py` lifecycle cover.
- **Actual gap:** projection richness (surface-level visual select, legend,
  working history, summary counts, read-only mode, responsive wrap) — not the
  data model, which is already better (8 surfaces vs 5, real resolve lifecycle).
- **Enhancement:** extend our odontogram natively (surface select on focused
  tooth, legend with fill+label+icon, history from resolved findings, read-only
  prop, wrap/scroll). Class **C** (recreate natively).

## 2. FDI tooth numbering

- **Theirs:** correct permanent ranges, midline-correct order, English tooth names.
- **Ours:** `PERMANENT_TEETH` frozenset 11–48, `validate_tooth` 422s anything else.
- **Actual gap:** none on permanent; both defer primary dentition.
- **Enhancement:** none now; primary-dentition scope is a dentist decision
  (discovery doc P-B). Class **D** for their ordering code (concept confirmed,
  no code needed).

## 3. Tooth surfaces + condition history

- **Theirs:** 5 fixed surfaces, yellow-dot-any-surface, `resolvedDate` modeled but
  filtered out of the UI (`isActive=true`).
- **Ours:** 8 surfaces (mesial/distal/occlusal/incisal/buccal/labial/lingual/palatal),
  lowercased/deduped, `uq_finding_surface`, resolve 409-guarded.
- **Actual gap:** visualization of per-surface state + surfacing resolved history
  in UI. No model gap.
- **Enhancement:** surface picker + history list in our chart UI. Class **C**.

## 4. Dental imaging + annotations

- **Theirs:** full viewer (zoom/pan/rotate/flip/B-C/fullscreen/keyboard) +
  canvas annotator (6 tools, undo/redo, normalized coords, read-only) persisted
  as `Document.annotations Json` via PUT route; upload accept list; annotation badges.
- **Ours:** `document_references` metadata pointers only
  (`DOC_TYPES={xray,scan,photo,report,other}`, `storage_key` required, bytes behind
  StoragePort, portal `download_available=false`). Encounter DocsTab explicitly
  notes "file upload and signed download URLs not available". **No viewer.**
- **Actual gap:** entire imaging interaction layer + upload/download plumbing
  (the metadata model already exists and must not be duplicated).
- **Enhancement:** build viewer + annotator adapted from their interaction
  vocabulary onto our tokens/storage/authz; annotations as new JSON-ish column
  or sidecar on our `document_references` via migration (design-gated). Class **B**.

## 5. Before/after image comparison

- **Theirs:** `image-compare.tsx` (slider + synced side-by-side), wired with
  max-2 sliding-window selection.
- **Ours:** nothing.
- **Actual gap:** same as (4) — comparison UX.
- **Enhancement:** adapt both modes with keyboard-accessible slider + dates
  always visible. Class **B**.

## 6. Treatment plans

- **Theirs:** list (filters/pagination/progress/cost/consent badge) → create
  (grouped procedures, editable costs) → detail (status-gated transitions,
  consent dialog, no-op Print). Client-side money math; free-text teeth.
- **Ours:** full lifecycle (`draft→active→completed/cancelled`, 5-state items,
  `activate` needs ≥1 item, cascade cancel), per-patient list/detail/recall pages,
  `ITEM_NEXT` gating, consent card, portal projections, isolation-tested.
- **Actual gap:** presentation only (progress bar + counts, consent badge,
  grouped procedure picker, deep-link item→record). No lifecycle gap — ours is
  stricter (server transitions, versioned, audited).
- **Enhancement:** adopt presentation ideas; never the money math. Class **D**.

## 7. Procedures catalogue

- **Theirs:** `Procedure` (code/name/category 10 values/basePrice/materials/
  pre+post instructions), grouped picker, settings page.
- **Ours:** `dental_procedures` (code UNIQUE/display/description/specialty/
  external_code/is_active), active-only ordered listing.
- **Actual gap:** catalog richness (categories, instructions) + admin curation UX;
  coverage itself unvalidated on both sides (dentist checklist item).
- **Enhancement:** dentist catalog-review session first (P-A); schema additions
  only if dentist requires. Class **D**.

## 8. Prescriptions

- **Theirs:** `Prescription/PrescriptionMedication/Medication` + form/tests.
- **Ours:** `modules/prescriptions` (draft→signed→cancelled, prescriber-only sign,
  versioned corrections) + encounter tab + portal page.
- **Actual gap:** none material.
- **Enhancement:** none. Class **E** (reject — redundant).

## 9. Clinical documents + consent

- **Theirs:** `Document` + `FormTemplate/FormSubmission` + consent flags on plans,
  signature-pad component + tests, verify/PDF routes.
- **Ours:** consents (single-subject XOR, decide once, withdraw) + document
  pointers; `modules/documents` is a stub; no signature capture, no text
  versioning, no vernacular support (known discovery gaps P-D).
- **Actual gap:** signature capture + consent-text versioning + rendering pipeline
  (print/PDF open decision, DESIGN.md §22).
- **Enhancement:** design signature-reference + text-versioning natively;
  their signature-pad is at most a concept reference. Class **D**.

## 10. Patient timeline

- **Theirs:** lazy tab, type filter, per-type icons, skeletons.
- **Ours:** encounters list + per-encounter notes/observations/diagnoses; no
  unified timeline view.
- **Actual gap:** unified chronological view across encounters/plans/records.
- **Enhancement:** timeline projection over existing rows (no new entities).
  Class **C** (their lazy-tab/filter pattern informs, code doesn't transfer).

## 11. Dental recall + follow-up

- **Theirs:** no dedicated recall page; cron (`6+mo no-visit, incomplete plans,
  overdue follow-ups` → AIInsight + notifications) + reminders/collections crons
  + trigger service.
- **Ours:** full recall CRUD + one-way transitions + per-patient queue page;
  **no reminders** (`request_notification` outbox only, no provider/templates).
- **Actual gap:** reminder fan-out + recall→appointment booking UX (both sides
  agree this is the gap; ours is explicit, theirs is cron+AI coupled).
- **Enhancement:** wire recalls to our notification outbox when provider lands
  (P8.1); reception recall→booking flow. Their cron bodies are concept reference
  only. Class **D**.

## 12. Lab orders

- **Theirs:** real module (orders/new/vendors pages, 12 work types, 9 statuses,
  quality check, documents, AI skill).
- **Ours:** missing (no `lab*` under `backend/`).
- **Actual gap:** entire lab-order workflow.
- **Enhancement:** future native module behind our tenancy/authz; their work-type
  list + status set are useful domain reference. Class **D** (no code).

## 13. Inventory + stock alerts

- **Theirs:** real module (items/batches/transactions/alerts/reports/suppliers,
  inventory cron, forecasting skills).
- **Ours:** `modules/inventory/__init__.py` one-line stub ("P4+ scope").
- **Actual gap:** entire module (out of current scope by design).
- **Enhancement:** none now; alert-threshold concept noted for P4+. Class **D/E**.

## 14. Sterilization tracking

- **Theirs:** real module (instruments/logs/reports pages + API).
- **Ours:** missing (no `steril*` anywhere).
- **Actual gap:** instrument/log workflow.
- **Enhancement:** future native module; their log shape is concept reference.
  Class **D**.

## 15. Patient communication

- **Theirs:** comms pages (analytics/automations/feedback), templates, SMS/email
  services, surveys, triggers, bulk send.
- **Ours:** notification request outbox only; comms architecture docs exist
  (`docs/commercial/communications-architecture.md`) but no provider.
- **Actual gap:** provider + templates (blocked, known).
- **Enhancement:** none from their code (SMS/email service code is backend to
  reject); trigger-event taxonomy is mild reference. Class **E** for code, **D** for ideas.

## 16. Patient portal

- **Theirs:** OTP portal (`PatientOTP`), booking, secure views, portal-shell + tests.
- **Ours:** full portal projections (plans/recalls/consents/billing/visits/
  documents-metadata, closed-only, drafts hidden, access log), tested.
- **Actual gap:** none structural; ours is more disciplined (release rules).
- **Enhancement:** consider their booking-from-portal flow as UX reference for
  our portal appointments (already exists: list/detail/cancel). Class **D**.

## 17. Dental reporting

- **Theirs:** reports pages + export API + export-menu + AI report-builder + skills.
- **Ours:** billing reports exist; no dental analytics surface; dentist-facing
  recall/consent/receipt list APIs are DESIGN.md §22 open decisions.
- **Actual gap:** recall board / consent list / plan-progress aggregates.
- **Enhancement:** server-filtered list APIs + TanStack tables per our patterns;
  their export-menu UX is mild reference. Class **D**.

## 18. Other: dashboard, search, notifications, queue/waitlist, insurance, video, chat

- **Dashboard tiles:** ours deliberately avoids tile walls (DESIGN.md). Reject aesthetic; adapt "today strip" idea only.
- **Global search** (`global-search.tsx`): debounce + `/` + keyboard nav is a good
  micro-pattern; adapt behind tenant-scoped minimal-PHI search. Class **B**.
- **Notification tray:** 60s poll + optimistic read is a good micro-pattern;
  adapt onto our outbox/portal APIs. Class **B**.
- **Queue/waitlist, insurance/pre-auth, payment plans, video consults, chat:**
  real there, out-of-scope or separately planned here. Reference only; reject code.
- **AI (16 skills, 16 routes, 11 UI files):** do not prioritize "merely because
  advertised as AI-powered" (brief §12). Reject wholesale — provider coupling,
  unvalidated clinical advice surface, no place in our architecture.
