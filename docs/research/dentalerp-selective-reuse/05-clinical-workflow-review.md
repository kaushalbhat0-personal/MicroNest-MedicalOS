# 05 — Clinical workflow review (dental-erp @ 389d9841 vs our model)

No clinical rules are invented here. Our clinical model is unchanged by this
audit. Uncertain semantics are flagged for dentist review, not decided.

## FDI and chart review

- **Numbering/orientation:** Their permanent ranges (18→11 / 21→28 / 31→38 /
  48→41, midline-correct, mirrored patient view, quadrant labels q1/q2/q4/q3)
  are clinically coherent and agree with our `PERMANENT_TEETH`. No conflict.
- **Primary dentition:** both sides unsupported (theirs: absent; ours:
  hard-rejected 51–85 with 422). If the clinic sees children this is a
  **blocker, not a nit** (discovery P-B). No reuse changes this — it needs a
  dentist scope decision + native schema/design work.
- **Surfaces:** theirs 5 (mesial/distal/occlusal/buccal/lingual, `occlusal`
  reused for anteriors); ours 8 (+incisal/labial/palatal, normalized/deduped,
  no anterior/posterior appropriateness rule — documented deferral). Their
  single-dot "any surface" rendering loses information our model keeps.
  Adaptation must render all 8 and respect anterior/posterior naming once the
  dentist rules on it — do not bake their 5-surface set into our UI.
- **Conditions/status semantics:** their 14-value enum (incl. BRIDGE as a
  tooth condition, SENSITIVE/MOBILITY as conditions) vs our condition catalog
  rows + finding `active/resolved`. "Bridge" is a prosthesis spanning teeth,
  not a single-tooth condition — flag for dentist: how should multi-tooth
  constructs be recorded in our finding model? Do not import their enum.
- **History:** their resolved-history UI is dead (`isActive=true` filter);
  our active→resolved lifecycle is real and tested. Our UI should display what
  our model already captures — no model change needed.
- **Resolved vs active:** our 409-guarded one-way resolve is sound; their chart
  has no resolve affordance at all. Keep ours.
- **Tooth→procedure linkage:** theirs links items to treatments via deep link
  (`/treatments/new?patientId=&procedureId=`); ours is referential
  (`plan_item_id` optional, no auto-sync) — discovery P-C open question
  (manual dual-tracking: acceptable or error-prone?). Dentist decision; do not
  automate silently either way.
- **Treatment stage tracking:** their plan statuses
  (DRAFT/PROPOSED/ACCEPTED/IN_PROGRESS/COMPLETED/CANCELLED) + item PENDING vs
  ours (draft/active/completed/cancelled + 5-state items). Ours is adequate and
  tested; a PROPOSED/ACCEPTED consent handshake exists in ours via the consent
  object rather than plan status — arguably cleaner. No change proposed.

## Imaging workflow

- Annotations are measurements/markup on diagnostic images: coordinates must be
  resolution-independent (theirs: normalized 0–1 — correct approach), authored
  + timestamped, and read-only once finalized. Their `annotations Json` +
  `annotatedBy/At` covers authorship; our adaptation needs the same plus tenant
  scope and encounter linkage (our document rows already carry both).
- Brightness/contrast/rotation/flip are **view-time projections**, never
  persisted (theirs gets this right — pure CSS). Keep that invariant: adjusting
  display must never rewrite the stored image or its annotations' meaning.
- Before/after comparison requires visible dates + same-modality pairing;
  their `{src,title,date?}` makes date optional — ours must require it.
- Annotation IDs must be UUIDs, not `Math.random` strings.

## Treatment lifecycle + consent/documentation

- Their consent handshake (PROPOSED→consent→ACCEPTED) vs ours (plan stays
  draft/active; separate consent object goes pending→granted/declined, withdraw
  supported, single-subject XOR, string `document_ref`). Ours separates clinical
  consent from plan state — keep. Open dentist questions (unchanged from
  discovery P-D): signature capture, consent-text versioning, vernacular
  support, and what suffices to replace paper.
- Their no-op Print button is a reminder: consent/plan printouts are an open
  DESIGN.md §22 decision — do not ship dead buttons; design the rendering
  pipeline first.

## Dentist sign-off checklist (nothing below is approved until walked through)

- [ ] Daily mix adult/child — primary-dentition scope (blocker if children seen).
- [ ] Condition catalog: keep/add/rename on seeded `dental_conditions`
  (caries/perio/endo/ortho/surgical coverage; "bridge"/"sensitive"/"mobility" semantics).
- [ ] Procedure catalog: does `dental_procedures` cover the real service mix?
- [ ] Surface model: is the 8-surface set with no anterior/posterior rule
  acceptable chair-side? (`incisal` vs `occlusal` vs `palatal`.)
- [ ] Finding→plan→record linkage: is manual referential linking acceptable, or
  must recording a procedure advance the plan item (and vice versa)?
- [ ] Consent: what must the software capture to replace paper today
  (signature? text version? vernacular? witness?)?
- [ ] Recall: who follows up, how, what "missed" means, recall→appointment booking?
- [ ] Billing: estimates always? part-payments? plan↔estimate linkage needed for
  informed financial consent?
- [ ] Imaging: which modalities (X-ray/CT/photo), annotation authorship rules,
  before/after pairing rules, retention?
- [ ] Odontogram chair-side test on tablet (touch targets, single-column, gloves).
- [ ] Portal: what should patients see (plans, recalls, images?)?
- [ ] Proposed imaging/annotation adaptation demo (mock data) — approve interaction
  vocabulary before any schema work.
