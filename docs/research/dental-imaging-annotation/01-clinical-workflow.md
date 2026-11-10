# 01 — Clinical Workflow: What Annotation Means

No clinical rules are invented here. Uncertain semantics are flagged as
dentist decisions (→ `09-open-decisions.md`, Q1–Q8). Our clinical model is
unchanged by this audit.

## 1. Annotation classes (do not conflate)

| # | Class | Persisted? | Clinical record? | Visible to |
|---|-------|-----------|------------------|------------|
| A | Temporary visual markup (unsaved overlay: a dragged rectangle while measuring) | No — dies with the session | No | Only the editing clinician |
| B | Draft annotation (saved work-in-progress) | Yes, editable | No — explicitly not a record | In-scope clinicians |
| C | Finalized annotation (signed-off overlay + metadata) | Yes, immutable revision | Yes — part of the encounter record | In-scope care team |
| D | Encounter finding (`ToothFinding` today) | Yes, existing lifecycle | Yes — the formal record | Team; selected projections to portal |

Rule: **an annotation is visual reference, never a clinical finding.**
Findings remain `ToothFinding` rows (`backend/app/modules/dental/service.py`:
FDI-validated, 8 surfaces, active→resolved, 409-guarded). An annotation may
*reference* a tooth/surface for display and linking, but creating one must
not assert pathology. If the dentist wants annotation→finding promotion,
that is a separate designed workflow (Q3), not a side effect.

## 2. Actors and capabilities (proposed; Q1 to confirm)

- **Author (create/edit draft):** holder of `DENTAL_RECORD` in the
  encounter's tenant+location scope (today: `doctor`, `tenant_admin` via
  `CLINICAL_ADMIN`; see `backend/app/platform/authz/permissions.py:63-77`).
- **Viewer:** holder of `DENTAL_READ` in scope (adds `nurse` read-only).
  No write path exists for readers — enforced server-side, never by UI.
- **Amend another clinician's draft:** permitted for any in-scope
  `DENTAL_RECORD` holder (clinical collaboration norm), fully attributed
  per item (`created_by`/`updated_by`); dentist to confirm or restrict to
  author-only (Q1).
- **Finalize:** same write permission; records `finalized_by/at`, freezes
  the revision. Whether finalization needs a second role (e.g. only the
  treating practitioner) is Q1.
- **Nurse/receptionist/accountant/staff/patient:** no authoring path
  (`nurse` lacks dental permissions entirely — correct specialty boundary;
  `patient` portal role has only `PORTAL_READ` + appointment-cancel).

## 3. Lifecycle questions and proposed answers

- **Can a finalized annotation be changed?** No in place. Corrections
  create a new revision (append-only; §4 in `04-persistence-design.md`).
  Matches existing norms: finalized notes use amend-new-version, consents
  use decide-once + withdraw, plans bump `version` on transition
  (`plans.py:201,226,251`).
- **Draft vs finalized:** both exist. Draft = editable, visibly watermarked
  as non-record (DESIGN.md §15 draft-watermark precedent); finalized =
  immutable, read-only, evidence-grade.
- **Superseded / archived:** superseded = prior revisions retained and
  inspectable (chain, never rewritten). Archived = not proposed; retention
  follows the record-retention policy (Q5). Do not invent a delete for
  finalized annotations.
- **Can annotations be deleted?** Draft items: yes (soft-delete,
  attributed). Finalized revisions: no deletion affordance in first
  release. Document-reference deletion: no delete endpoint exists today
  (`document_references.encounter_id` is `RESTRICT`), so cascade semantics
  are moot — note for retention review (Q5).
- **Author leaves the clinic:** attribution is a stored user id + display
  snapshot (`created_by`, `author_display`), never a live join for meaning;
  history stays intact and inspectable. Exact PII-in-snapshot rules need
  privacy confirmation (part of Q1).
- **Image replaced / new upload:** a new upload is a **new document
  reference** (immutable pointer model), so annotations stay bound to the
  exact bytes they were drawn on. No transfer, no re-projection. The UI
  must show which reference a revision belongs to (Q5 for retention of
  superseded images).
- **Tooth/surface association:** optional per-item fields, validated by
  the existing validators (`validate_tooth`, `validate_surface` in
  `dental/service.py:38-61`; permanent dentition only, P-B unchanged).
  Whether a tooth link implies anything clinical is Q3.

## 4. Evidence and planning use

A finalized annotation may be *cited* as evidence for a treatment plan
(display link only). It must not auto-create plan items or findings —
the manual-referential-linking question (discovery P-C, audit §05) applies
here unchanged and is explicitly out of scope for first release.

## 5. Visibility

- In-scope clinicians: drafts (marked) + finalized (record).
- Other locations/tenants: nothing (existing scoping, no per-patient
  grants — same rule as D1b).
- Patients/portal: **excluded until explicit policy approval** (Q6).
  `PortalDocument.download_available` is hardcoded `False`
  (`portal/schemas.py:147`); annotations get no portal field at all in
  first release.
