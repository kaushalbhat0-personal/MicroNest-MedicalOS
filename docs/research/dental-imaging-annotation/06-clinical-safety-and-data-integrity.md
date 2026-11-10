# 06 — Clinical Safety and Data Integrity

## 1. Original-image immutability

- Bytes: never rewritten — annotations are vector data in separate tables
  (`04-…​`), rendered client-side over the signed-URL image. No
  flattened-derivative write path exists in first release (see §5).
- Reference row: no UPDATE path introduced (`document_references` keeps
  its pointer-only shape; D1c viewer already never exposes storage keys).
- View transforms (zoom/rotate/flip/B-C) stay CSS projections
  (`imaging-transform.ts`, D1 invariant) — annotation mode adds no
  transform that writes back.

## 2. Original vs annotated presentation

- Overlay defaults **ON in view of finalized sets, OFF one toggle away**:
  "Show original" is always a single action (button + keyboard), and the
  mode visibly distinguishes states: draft watermark (non-record) vs
  finalized badge (record) vs original (no overlay). Never color-only —
  text labels per DESIGN.md §2.3.
- The finalized overlay must show author + revision + timestamp (minimal,
  non-PHI-beyond-chart), so a second clinician knows whose eyes marked
  what and when.
- Misleading-overlay rules: shapes scale with the image (they mark
  anatomy); strokes/labels stay legible via `non-scaling-stroke`; no
  overlay may obscure the underlying anatomy without the one-action
  original view; annotation list numbers match overlay numbers exactly.

## 3. Lifecycle safety

- Finalized revisions immutable (no UPDATE path in service; enforced by
  tests in `07-…​`). Corrections = new revision with supersede chain —
  same family as finalized-note amend and consent withdraw, satisfying
  DESIGN.md §10/§13 ("never render Edit on immutable records; render the
  correction affordance").
- No silent replacement: every post-finalize change is a visible new
  version with author + reason (reason capture is Q4).
- No deletion of finalized history in first release (retention = Q5).

## 4. Patient visibility (excluded by default)

Portal stays annotation-free: no annotation fields on `PortalDocument`,
`download_available` remains `False`, no signed-URL or overlay data to
portal clients. Patient visibility requires explicit policy + dentist
approval (Q6) and would be a separately gated projection (finalized only,
watermarked, read-only) — not a flag flip.

## 5. Storage and export (first release: overlay only)

- Render annotations as overlay; **no flattened derivative, no
  download/export/print/attach-to-report** in first release. Rationale:
  a flattened PNG becomes a new clinical artifact needing its own
  retention/audit/portal rules (all Q5/Q6); shipping it early creates
  record-keeping debt.
- Future export path (non-committal): server-side render of
  revision-payload + original bytes → new `document_references` row
  (`doc_type` e.g. `annotated` — needs dentist sign-off) linking
  `source_document_id`, preserving original + history. Original and
  revision history remain untouched by construction.
- Interoperability (DICOM/FHIR ImagingStudy/Media later): per-object
  rows in Option B map cleanly (annotation ↔ body-site/tooth coding);
  JSON-blob options would not — one more reason for B (`04-…​§4`).
  No interoperability work is proposed now.
