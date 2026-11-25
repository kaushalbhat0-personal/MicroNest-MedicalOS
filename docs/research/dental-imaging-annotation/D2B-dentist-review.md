# D2B — Dentist Clinical Decision Resolution (Review Questionnaire)

**Status:** AWAITING DENTIST REVIEW. No answers assumed, no approval claimed.
**Authority:** `docs/research/dental-imaging-annotation/09-open-decisions.md` (Q1–Q8).
No annotation schema, migration, endpoint, or UI work starts until Q1–Q8 are
explicitly resolved. Technical recommendations (T1–T6) are the team's call
and need no dentist action; they are listed only for transparency.

## How to respond

For each question: **Approve proposal / Approve with changes / Defer**.
Record the decision, date, and who approved in the table at the end.

## Q1 — Authorship and finalization (blocks backend design)

Proposal: any in-scope doctor (holder of the dental write permission) may
author and finalize; any in-scope doctor may amend another doctor's *draft*,
fully attributed; finalized annotations are immutable and corrections create
a new version (same as today's finalized notes and consents).
Consequence of approval: any covering doctor can finish a colleague's draft.
Consequence of restriction (author-only): drafts can stall when the author is
absent; the software will enforce author-only editing instead.

## Q2 — First-release tool scope (blocks UI build)

Proposal: numbered markers, rectangles, short text labels, select/move/delete,
undo/redo, overlay toggle, save/finalize. Freehand, arrows, ellipses,
colour pickers, and measurement rulers are explicitly OUT of first release.
Consequence: marking "watch this spot" and "region of interest" is covered;
artistic/measurement markup is not. (Uncalibrated on-screen measurement is
refused for safety — the software stores no millimetre calibration.)

## Q3 — Tooth/surface linkage (blocks schema detail)

Proposal: an annotation may carry an *optional display link* to a tooth
(and surface) for filtering and display only. Creating or editing an
annotation never creates or changes a formal finding, plan item, or record.
Consequence of asking for promotion (annotation → finding): a separately
designed workflow with its own approvals; not built by default.

## Q4 — Corrections (blocks lifecycle rules)

Proposal: finalized annotations cannot be edited; a correction creates a new
visible version with author, timestamp, and reason; all prior versions stay
inspectable (as with amended clinical notes).
Consequence: the record only ever grows; nothing is silently rewritten.

## Q5 — Retention and image replacement (blocks retention note)

Proposal: annotations stay bound to the exact image they were drawn on; a
re-taken image starts empty (old image and its annotations are retained).
Finalized history is never deleted; retention period and legal-hold rules to
be stated by the clinic: ___ years. Confirm whether document references must
remain non-deletable (current behaviour).

## Q6 — Patient visibility (blocks any portal work; default: excluded)

Proposal: patients see NO annotations and NO image downloads in first
release. Any future patient-visible projection would be finalized-only,
watermarked, read-only, and separately approved.
Consequence of approval-as-proposed: zero portal changes.

## Q7 — Before/after comparison pairing (blocks future compare only)

Proposal (for later, not first release): comparison requires same modality
and visible dates on both images. No decision needed now unless the clinic
wants different pairing rules recorded early.

## Q8 — Primary dentition (pre-existing, blocks paediatric scope)

Confirm: does the clinic image children's teeth? If yes, primary-dentition
support must be designed before annotation covers those cases.

## Technical recommendations (no dentist action needed)

Per-mille integer coordinates; SVG overlay sharing the viewer transform;
dedicated annotation tables with immutable revision snapshots; existing
read/write permissions with unchanged tenant+location scoping; no AI, no
export, no flattened copies in first release.

## Decision log

| Q | Decision | Approved / deferred by | Date |
|---|----------|------------------------|------|
| Q1 | | | |
| Q2 | | | |
| Q3 | | | |
| Q4 | | | |
| Q5 | | | |
| Q6 | | | |
| Q7 | | | |
| Q8 | | | |
