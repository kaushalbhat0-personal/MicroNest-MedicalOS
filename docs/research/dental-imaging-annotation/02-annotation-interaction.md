# 02 — Annotation Interaction Model

Reference: DentalERP RC-2 (`image-annotator.tsx`, 632 lines): 6 tools,
dual-canvas overlay, aspect-preserving fit, text flow, snapshot undo/redo,
ClearAll, `onSave`, read-only mode. Verified gaps to close in adaptation:
mouse-only canvas (WCAG gap), `Math.random` ids, swallowed errors, no
author-vs-viewer authz. Concepts adapt; code does not transfer.

## 1. Where the interaction lives

**Dedicated annotation mode inside the existing DocsTab viewer section —
not a new route, not a separate workspace.**

- The `ClinicalImageViewer` stays read-only by default (`packages/ui/imaging.tsx`).
  An "Annotate" toggle (DENTAL_RECORD holders only; others never see it)
  switches the viewer section into annotation mode: overlay becomes
  interactive, view-transform controls stay available, Save-draft /
  Finalize / Discard actions appear.
- Rationale: keeps the proven D1c retrieval/lifecycle flow; preserves the
  read-only viewer contract; no route, navigation, or signed-URL handling
  changes (mode switch never re-mints — same in-memory URL).
- Rejected: separate annotation workspace (splits context from the
  encounter chart, duplicates retrieval orchestration for no gain).

## 2. First-release tools (essential)

1. **Numbered markers** (primary tool). Click/tap drops a numbered pin;
   number pairs with the annotation list (no color-only meaning, DESIGN.md
   §2.3). Covers "watch distal of 16"-style callouts.
2. **Rectangles.** Drag to define a region of interest; keyboard path =
   list-driven placement at center + arrow-key nudge (see §4).
3. **Text labels.** Short label attached to a marker/rectangle anchor
   (max ~140 chars, plain text, no PHI beyond what the chart already shows).
4. **Select / move / delete** (draft only). Pointer drag + keyboard nudge;
   delete soft-deletes with attribution.
5. **Undo / redo.** Command-stack (not DentalERP snapshot-stack: cheaper,
   exact, auditable as draft edits, not record events).
6. **Overlay visibility toggle.** "Show annotations / show original" —
   the unmodified original must always be one action away (§6 doc).
7. **Save draft / Finalize / Discard** with explicit buttons, pending and
   saved states (DESIGN.md §11), and a draft watermark until finalized.

## 3. Useful later (deferred, not rejected)

- Ellipse/circle, arrows, freehand pen, polygon; per-item color/stroke
  picker (fixed accessible palette only — arbitrary colors forbidden by
  DESIGN.md §3); measurement (mm calibration needs modality metadata we
  do not store — do not ship uncalibrated rulers); before/after annotated
  compare (RC-3, needs Q7 pairing rules); annotation search/filter by
  tooth across encounters.

## 4. Not without clinical approval

- Anything that looks diagnostic: auto-detection, severity badges,
  "suggest finding" prompts, AI interpretation (rejected wholesale per
  audit §12/§18). Brightness/contrast disclaimer already in the viewer
  ("do not improve diagnostic accuracy") extends to annotation mode.
- Flattened-image export/print/attach-to-report (see `06-…​§5`).
- Patient-visible annotations (Q6).

## 5. Keyboard and screen-reader path (closes the RC-2 gap)

Every canvas/pointer operation gets a list-driven equivalent:

- Annotation list (ordered, numbered, tooth + label text) is the SR path:
  list items are focusable, expose actions (rename label, nudge, delete),
  and moving focus to an item highlights the overlay shape (and vice versa).
- Arrow keys nudge the selected shape (with the same 40px-step convention
  family as `PAN_KEY_STEP`); `Delete` removes (draft); `Ctrl+Z/Y` undo/redo;
  `Escape` exits mode or deselects. All shortcuts disclosed in the mode's
  hint text (viewer already does this; `imaging.tsx:411-417`).
- Touch: 44px minimum targets (DESIGN.md §8); tap = select/place;
  drag = draw/move; pinch remains view-zoom (must not draw).

## 6. Save/discard semantics

- Autosave is **not** proposed: explicit Save-draft keeps the clinical
  intent unambiguous and avoids half-drawn records. Unsaved overlay state
  is class-A ephemeral markup (see `01-…​§1`); navigating away prompts
  with the standard unsaved-changes pattern, never silent loss or silent
  save.
- Finalize requires an explicit confirm (destructive-protection pattern,
  DESIGN.md §21) and is one-way in first release (reopen = Q4).
