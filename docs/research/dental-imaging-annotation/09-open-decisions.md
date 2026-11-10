# 09 — Open Decisions

## Dentist / clinical-owner decisions (blockers hold P2)

- **Q1 — Authorship and finalization.** Who may author (treating doctor
  only, or any in-scope DENTAL_RECORD holder)? May a second clinician
  amend another's draft? May finalization be done by someone other than
  the author? What author snapshot is shown after staff departure?
  (Proposal in `01-…​§2-3` is a default, not approval.)
- **Q2 — Tool scope.** Are markers + rectangles + labels sufficient for
  first release? Is freehand/arrow/ellipse explicitly out?
- **Q3 — Tooth/surface linkage semantics.** Optional display link vs
  evidence link vs finding promotion (promotion NOT recommended).
  Anterior/posterior naming acceptability carries over (P-A/P-C).
- **Q4 — Corrections.** Is append-only revision without reopen acceptable?
  Is a reason/diagnosis-code required on amendment? Witness rules?
- **Q5 — Retention and replacement.** Retention years + legal hold;
  superseded-image retention; reference-deletion policy (currently no
  delete endpoint — keep or design?).
- **Q6 — Patient visibility.** Default: excluded. Any finalized-only
  portal projection needs policy + dentist approval (separate gating).
- **Q7 — Before/after pairing.** Same-modality/date-required rules before
  any compare work (carries over from audit §05).
- **Q8 — Primary dentition (P-B).** Pre-existing blocker; unchanged.

## Technical decisions (team can make independently)

- **T1.** Per-mille integer storage — adopted (§03-§2).
- **T2.** SVG overlay + shared transform — adopted (§03-§3).
- **T3.** Dedicated tables over JSON options — recommended (§04).
- **T4.** Payload caps (items/set, label length) — set in D2.
- **T5.** Idempotency window duration — set in D2.
- **T6.** No new permissions — decided (§05-§1); revisit only if Q1
  demands a distinct finalizer role (still expressible via DENTAL_RECORD
  + authorship rule, so unlikely).

## Non-blockers confirmed

No storage changes, no viewer redesign, no permission changes, no
DentalERP code, no portal changes needed for first release. The only
gates are clinical (above), not technical.
