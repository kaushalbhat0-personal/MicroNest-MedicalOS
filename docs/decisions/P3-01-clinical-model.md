# P3-01 Clinical Model (implementation decision record)

Date: 2026-11-02 · Status: implemented, awaiting architecture review.

## Encounter vs Appointment

Appointments schedule time; encounters contain care. An encounter MAY link
an appointment (`appointment_id` nullable, tenant-matched, same-patient
enforced) but never requires one — walk-ins open encounters directly.
Appointment lifecycle (scheduled/confirmed/…) and encounter lifecycle
(open/closed) are independent state machines in separate modules.

## Encounter lifecycle (single source: `clinical/service.py`)

`open → closed`, terminal. No reopen: closure finality is what makes
downstream clinical facts trustworthy.

## Closure ceremony (`close_encounter`, the only closer)

Closing requires, in order: encounter open; location scope; provider
attribution (`closed_by` = caller); a finalized note OR explicit
`note_waiver`; vitals (any observation) OR explicit `vitals_waiver`; and an
open-items check (draft prescriptions and draft treatment plans linked to
the encounter block closure, surfaced as 409 with item counts). Optional
≤200-char reason. Version increments on every transition.

## Immutability / corrections

Finalized rows are never UPDATE-mutated (there is deliberately no update
endpoint on any clinical resource). Corrections use supersede chains:

- notes: `draft → finalized → amended`; `amend_note` creates a new
  finalized version (`supersedes_id` set, version+1) and links the old row
  (`status=amended`, `superseded_by_id`). Original content untouched.
- observations: immutable rows; `amend_observation` creates a correction
  row (`corrects_id`) and marks the old row (`corrected_by_id`).
- diagnoses: `active → resolved/ruled_out/superseded`;
  `supersede_diagnosis` creates the replacement and marks the old row.
- prescriptions: `draft → signed → cancelled`; `correct_prescription`
  creates a new draft version (`version+1`, `supersedes_id`); the signed
  row is never edited (only its `superseded_by_id` link). Cancel is a
  lifecycle event, retry-safe (already-cancelled is a no-op success).
- Only the note author may finalize; only the prescriber may sign.

## Observations

Typed + catalog-backed (`observation_types`: bp systolic/diastolic, pulse,
temperature, respiratory rate, SpO2, height, weight). Range validation
against catalog min/max; `NUMERIC(12,3)` storage with unit snapshot per row
(units stay correct even if the catalog later changes). BP is recorded as
two separate coded observations (no composite/component modeling in P3).

## Diagnoses

Internal catalog (`diagnosis_codes` with ICD-10/SNOMED mapping columns, no
live terminology service — MVP vocabulary seeded in migration 0008).
Encounter rows carry exactly one of `diagnosis_id` / `free_text` (CHECK
enforced); free-text rows get `review_needed=true`, coded rows inherit the
catalog flag. Categories (active/resolved/ruled_out/superseded) are the
only mutation axis.

## Audit / events

Lifecycle transitions append to the existing hash-chained audit stream
(refs only — no SOAP text, instructions, free-text diagnoses, or document
content). No new outbox event types in P3: no downstream consumer exists
yet; business logic stays synchronous.
