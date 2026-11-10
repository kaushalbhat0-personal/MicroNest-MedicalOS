# Dental Imaging Annotation — Research Package (D2A)

**Phase:** READ-ONLY discovery and design. No implementation.
**Date:** 2026-11-10. **Baseline:** branch `main`, HEAD `efefb0a3`.
**Authoritative app:** FastAPI modular monolith · PostgreSQL/SQLAlchemy/Alembic ·
Next.js 16 / React 19 / TypeScript · `DESIGN.md` is the UI source of truth.

## Verdict: READY WITH CLINICAL DECISIONS

The architecture is fully designed and technically implementable without
inventing clinical rules. Implementation must wait on dentist sign-off for
the items in `09-open-decisions.md` — most critically annotation authorship
and lifecycle semantics (Q1), tool scope (Q2), and patient visibility (Q6).
No technical blocker was found: no new permissions, no storage changes, no
viewer redesign, and no DentalERP code are required.

## Scope

- D1 (viewer, presentation-only transforms), D1b (authorized signed-URL
  grant), D1c (DocsTab integration, in-memory URLs, 30 web + 17 UI tests)
  are built, tested, and unchanged by this design.
- This package designs **clinician-authored vector annotations over the
  original image coordinate system**, persisted as versioned clinical
  records, rendered as a toggleable overlay. It does not redesign viewing,
  storage, or authorization.

## Recommended approach (one paragraph)

Add a dedicated **annotation mode** inside the existing DocsTab viewer
section (not a new route; the viewer stays read-only by default). Store
annotations in **dedicated tables** (`image_annotation_sets` +
`image_annotation_items` + immutable `image_annotation_revisions`),
keyed to the immutable `document_references` row, with draft → finalized
lifecycle, per-set optimistic concurrency, and append-only corrections.
Coordinates are **normalized per-mille integers (0–1000)** in original
image space with exact quarter-turn/flip inverse mapping; overlay is SVG
(not canvas) for DPR-independence and keyboard/screen-reader access.
Authorize with existing `DENTAL_READ` (view) / `DENTAL_RECORD` (author)
plus unchanged tenant+location scoping. Render overlay only — never a
flattened derivative — and keep portal/downloads excluded until explicit
policy approval.

## Documents

1. `01-clinical-workflow.md` — actors, annotation classes, lifecycle questions.
2. `02-annotation-interaction.md` — tool model; first release vs later vs never-without-approval.
3. `03-coordinate-architecture.md` — normalized space, transform math, pseudocode, edge cases.
4. `04-persistence-design.md` — options A/B/C comparison, recommended schema, revisions.
5. `05-authorization-and-audit.md` — permission matrix, scoping, authorship, audit events.
6. `06-clinical-safety-and-data-integrity.md` — immutability, visibility, retention.
7. `07-testing-strategy.md` — unit/API/DB/security/E2E matrix.
8. `08-implementation-plan.md` — ordered phases, gates, exclusions.
9. `09-open-decisions.md` — dentist vs technical decisions, blockers.

## Open clinical decisions (must not be assumed)

Q1 authorship/lifecycle · Q2 tool scope · Q3 tooth/surface linkage semantics ·
Q4 correction/amendment rules · Q5 retention/image-replacement · Q6 patient
visibility · Q7 before/after pairing rules · Q8 primary-dentition scope
(pre-existing P-B). Details in `09-open-decisions.md`. The dentist
walkthrough in `05-clinical-workflow-review.md` of the DentalERP audit
remains the gate before any schema work.

## Provenance

- DentalERP (`abinauv/dental-erp` @ `389d9841`) used as **reference only**
  via the completed audit (`docs/research/dentalerp-selective-reuse/`,
  esp. RC-2 findings: 6 tools, normalized coords, undo/redo, read-only,
  UUID ids, PUT persistence). No code copied, no dependency adopted.
- All Healthcare OS claims verified against the current tree (paths cited
  per document), not carried over from prior reports.
