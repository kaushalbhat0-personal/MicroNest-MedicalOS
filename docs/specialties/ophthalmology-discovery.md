# Ophthalmology specialty discovery (Pilot B)

Status: discovery ONLY. No tables, no endpoints, no clinical logic in this slice.
Constraint: do not invent thresholds, diagnostic rules, or treatment logic.
Context: the supplied clinic website is background only — it does not define
the doctor's workflow. Everything below must be validated with the ophthalmologist.

Integration frame: shared core (`encounters`, `clinical_notes`, `observations`,
`encounter_diagnoses`, `prescriptions`, `treatment_plans`? no — dental plans are
dental-scoped) stays specialty-neutral. Ophthalmology, if approved, lands as a
new `ophthalmology` module beside `dental`, reusing: tenant scope, location
scope, practitioner verification, encounter lifecycle, note finalize/amend
chains, observation range checks, prescription sign flow, billing, portal
release rules, audit-ID-only discipline. No shared-core contamination, no
dental-table reuse.

How to read each row: why it may be needed → what the doctor must confirm →
core-vs-module → structured-vs-narrative → laterality → units/ranges/terminology
→ Rx/billing effect → portal visibility.

## 1. Registration + history

- Why: eye patients skew older; systemic history (diabetes, hypertension),
  ocular history (surgery, trauma, glasses/contact lens), allergy and
  medication history change examination and prescribing.
- Confirm: minimum history dataset; systemic vs ocular sections; who captures
  (reception vs doctor); whether history must be structured or free-text SOAP suffices.
- Core vs module: shared `clinical_notes` SOAP may suffice for v1; structured
  history items would be a module table (needs approval).
- Structured vs narrative: TBD by doctor — do not assume.
- Laterality: n/a for systemic; ocular history may need eye-level granularity.
- Units/ranges/terminology: none yet; terminology mapping (ICD/SNOMED for
  ophthalmic diagnoses) TBD.
- Rx/billing: history depth does not bill directly.
- Portal: history is clinical — closed-encounter finalized-only if shared.

## 2. Eye-specific history (presenting complaint, duration, eye involved)

- Why: laterality-first triage (which eye, since when, pain/vision-change/redness/trauma).
- Confirm: required fields for a new visit; whether bilateral complaints need
  two entries or one with laterality flag.
- Core vs module: chief_complaint on encounter exists (500 chars, unstructured).
  Structured eye-complaint rows would be module scope.
- Structured vs narrative: TBD.
- Laterality: yes — right / left / bilateral (+ "unspecified" handling TBD).
- Units/ranges: duration units (days/weeks/months) TBD, no thresholds invented.
- Rx/billing: no direct effect.
- Portal: same release rule as notes if structured later.

## 3. Laterality primitive (right / left / bilateral)

- Why: nearly every ophthalmic fact is eye-scoped. A wrong-eye error is a
  patient-safety event.
- Confirm: allowed values; whether "bilateral" means one row or two;
  display convention (OD/OS/OU vs Right/Left/Both); wrong-eye safeguards
  the doctor expects in UI (explicit eye badge on every surface — mirrors the
  dental "patient always unambiguous" rule, DESIGN.md §2).
- Core vs module: a module-level convention (check constraint + UI badge),
  never a shared-core column.
- Structured: enum, not free text (exact values need doctor sign-off).
- Units: n/a. Terminology: OD/OS/OU mapping TBD.
- Rx/billing: laterality may appear on prescriptions/procedure descriptions —
  confirm whether billing lines must carry eye information.
- Portal: eye labels must be unambiguous to patients; confirm wording.

## 4. Visual acuity (unaided / aided, distance / near, pinhole)

- Why: core eye-exam vital; determines visit trajectory.
- Confirm: chart/method used (Snellen/LogMAR/near chart); notations accepted
  (6/6, 20/20, decimal, counting fingers, hand motion, light perception —
  do NOT hardcode without doctor input); which conditions (unaided, with
  glasses, pinhole) are recorded; per-eye requirement.
- Core vs module: shared `observations` support typed numeric facts with ranges —
  but acuity notations are not plain numerics. If structured, module table with
  notation-aware validation; else narrative note. Doctor decides.
- Structured vs narrative: TBD — default to narrative until the doctor picks
  the notation set.
- Laterality: yes, per eye (+ condition per eye).
- Units/ranges/terminology: notation set + allowed values TBD; no invented ranges.
- Rx/billing: no direct billing; affects refraction/prescription decisions (doctor's judgment).
- Portal: confirm whether patients should see acuity values (interpretation risk).

## 5. Refraction (objective / subjective, sphere / cylinder / axis, add)

- Why: glasses prescription source data.
- Confirm: data elements captured (sphere, cylinder, axis, add, PD, prism?);
  objective vs subjective vs final; whether the system must compute anything
  (default: no — UI displays, doctor decides; mirrors billing "never compute" discipline).
- Core vs module: module scope if structured.
- Structured vs narrative: TBD; numeric fields need units (diopters, degrees) and
  axis range conventions confirmed by the doctor — not invented here.
- Laterality: yes, per eye.
- Units/ranges: diopters / degrees / mm (PD) — exact ranges TBD by doctor.
- Rx/billing: feeds spectacles prescription (optical order, not systemic Rx);
  confirm whether optical orders need billing lines.
- Portal: glasses prescription is the highest-value portal artifact for eye
  patients — confirm format (print/PDF open decision applies).

## 6. Intraocular pressure (IOP)

- Why: glaucoma screening/monitoring; method-dependent values.
- Confirm: measurement method(s) used (non-contact, applanation, rebound);
  whether method must be recorded alongside value; time-of-day relevance;
  per-eye requirement.
- Core vs module: closest fit to shared `observations` (numeric + unit + range)
  IF the doctor accepts method-as-text; else module row with method enum.
- Structured vs narrative: TBD.
- Laterality: yes, per eye.
- Units/ranges: mmHg presumably — confirm unit + plausible range with the doctor;
  nothing hardcoded here.
- Rx/billing: monitoring cadence may drive recalls, not billing lines.
- Portal: confirm visibility (a bare number without interpretation may alarm).

## 7. Slit-lamp examination (anterior segment per structure)

- Why: lids, conjunctiva, cornea, anterior chamber, iris, lens — structured
  narrative per structure per eye.
- Confirm: structure list; grading scales used (if any — do not invent);
  drawing/sketch needs; photo attachment needs.
- Core vs module: narrative fits shared notes today; structured grades would
  be module scope with doctor-defined scales.
- Structured vs narrative: TBD; default narrative.
- Laterality: yes.
- Units/ranges/terminology: grading scales TBD (no invented scales).
- Rx/billing: findings may justify procedures — confirm linkage needs.
- Portal: confirm how much anterior-segment detail patients should see.

## 8. Fundus examination (posterior segment, dilation status)

- Why: disc, macula, vessels, periphery; dilation changes what was examinable.
- Confirm: structures documented; dilation status capture (dilated yes/no,
  agent, time); drawing/photo needs; referral triggers (doctor's judgment, not rules).
- Core vs module: same as slit-lamp — narrative now, module later if structured.
- Laterality: yes.
- Units/ranges: cup-disc ratio notation TBD (no invented validation).
- Rx/billing: may drive imaging orders.
- Portal: confirm visibility + interpretation wording.

## 9. Diagnosis (ophthalmic coding)

- Why: cataract, refractive error, glaucoma suspect, retinal findings, etc.
- Confirm: whether shared `diagnosis_codes` catalog can carry ophthalmic codes
  (ICD-mapped rows added as data) or a module-specific catalog is needed;
  free-text vs coded balance; laterality on diagnosis rows (shared model has
  no laterality — module extension or convention?).
- Core vs module: prefer shared diagnoses + data rows if the doctor accepts;
  laterality handling is the open design question.
- Structured: coded XOR free-text already exists — confirm sufficiency.
- Laterality: REQUIRED design answer.
- Terminology: ICD/SNOMED mapping for ophthalmic set TBD.
- Rx/billing: diagnosis may justify procedures — no auto-rules.
- Portal: active/resolved diagnoses on closed encounters (existing rule).

## 10. Prescriptions (systemic/ocular medications + glasses)

- Why: eye drops (eye, frequency, duration), systemic meds, glasses.
- Confirm: drop-specific fields (which eye, drops vs ointment); glasses
  prescription format (separate artifact from medication Rx?); duration/quantity
  conventions; vernacular instructions needs.
- Core vs module: shared prescriptions fit systemic/ocular meds (signed-only
  portal rule already); spectacles may be a module artifact — doctor decides.
- Structured: medication catalog rows are data (ophthalmic drops added as data
  if prescribed); glasses fields TBD.
- Laterality: yes for drops (which eye) — shared Rx items have no laterality
  today; design gap to resolve with the doctor.
- Units/ranges: dose/route/frequency/duration conventions TBD.
- Rx/billing: signed Rx is the legal record; confirm re-print needs.
- Portal: signed-only (existing); glasses copy — confirm.

## 11. Procedures (in-clinic + surgical: e.g. foreign-body removal, laser, injections, cataract workup steps)

- Why: procedure records + consents + billing mirror dental's shape but with
  eye-specific catalog and laterality.
- Confirm: in-scope procedure list for v1 (clinic-only vs OT); whether
  dental-style plan→record→consent→estimate→invoice fits eye workflows or a
  simpler record+consent+bill suffices; surgical consent specifics.
- Core vs module: module catalog + records mirroring dental's state machines
  (do not reuse dental tables); billing shared.
- Laterality: yes — mandatory on every eye procedure row.
- Units/terminology: catalog displays TBD with the doctor.
- Rx/billing: procedure → billing line linkage is manual today (as in dental);
  confirm acceptability.
- Portal: mirror dental release (plans/records/consents/recalls issued-financials).

## 12. Follow-up / recall

- Why: post-procedure review, IOP recheck, post-refraction review.
- Confirm: recall reasons used; intervals (doctor-set per recall, no auto-rules);
  whether eye recalls need eye-level context; reminder expectations (blocked on
  real notifications — set expectations now).
- Core vs module: shared `recalls` shape likely fits (patient + location +
  due_date + reason); eye-context extension only if the doctor requires.
- Portal: existing recall list fits.

## 13. Referral (retina / cornea / glaucoma / neuro-ophthalmology)

- Why: independent clinics refer out; referral letters matter.
- Confirm: referral letter content + print needs; whether referrals need
  structured tracking (to whom, when, report back) or document-only.
- Core vs module: document reference exists; structured referral tracking
  would be module scope — confirm need.
- Portal: referral letters contain PHI — confirm release policy with the doctor.

## 14. Patient instructions (drops regimen, post-dilation precautions, red-flags)

- Why: adherence + safety-netting; high value in eye care.
- Confirm: instruction formats (vernacular?); print/handout needs; whether
  instructions should be portal-visible after the visit.
- Core vs module: note-plan text exists; structured instruction sheets TBD.
- Portal: likely the most-read artifact — confirm language + content policy.

## 15. Documents + imaging (fundus photos, OCT, visual fields, biometry)

- Why: eye care is imaging-heavy; storage + retrieval + comparison over time.
- Confirm: modalities in scope for v1; file sizes; comparison needs (side-by-side
  across visits); retention expectations; consent for photos.
- Core vs module: `document_references` metadata + StoragePort already fit;
  viewer/comparison is frontend scope — confirm priority.
- Portal: metadata-only, closed-encounter-only, no downloads in this release
  (existing honesty) — confirm whether eye patients expect image access.

## 16. Explicit non-goals for v1 (unless the doctor overrides)

- No diagnostic thresholds or treatment rules in code (no "if IOP > X then …").
- No device integration (autorefractor/OCT import) until workflow is settled.
- No optical inventory (frames/lenses stock) — inventory module exists but
  optical retail is out of scope until confirmed.
- No new tables until this document is reviewed and the domain model is approved.

## 17. Questions for the ophthalmologist visit

1. Walk one new + one review visit end-to-end (synthetic patient): history →
   acuity → refraction → IOP → slit-lamp → fundus → diagnosis → Rx/advice →
   follow-up. Which steps must be structured vs narrative?
2. Laterality convention: OD/OS/OU or Right/Left/Both? One bilateral row or two?
3. Acuity + refraction notations accepted; glasses prescription format + print needs.
4. IOP methods used; must method travel with the value?
5. Slit-lamp + fundus structure lists and any grading scales (bring examples).
6. Diagnosis coding: shared catalog + laterality convention acceptable?
7. Drops prescribing: which-eye field mandatory? Glasses separate artifact?
8. Procedures in scope for v1 + consent practice today.
9. Follow-up intervals + reminder expectations (set notification honesty).
10. Imaging modalities + comparison + portal expectations.
11. Referral + instruction handout formats and languages.
