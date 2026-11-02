# P3-02 Dental Model (implementation decision record)

Date: 2026-11-02 · Status: implemented, awaiting architecture review.

## Extension direction

`patients → encounters → clinical → dental`. Dental consumes patient,
encounter, and practitioner IDs plus generic diagnosis primitives. It
creates no DentalPatient, no DentalAppointment, no billing/invoice/payment
tables — those layers are untouched by P3.

## FDI representation (single authority: `dental/service.py`)

`validate_tooth` accepts permanent dentition only
(11–18, 21–28, 31–38, 41–48). Primary dentition (51–85) is explicitly
deferred — the validator is the one place that rule lives. Surfaces are a
domain-controlled set (`mesial/distal/occlusal/incisal/buccal/labial/
lingual/palatal`, normalized lowercase, deduplicated); anterior/posterior
appropriateness is not enforced in P3. No odontogram table exists: the
odontogram is a UI projection derived from finding rows, never stored.

## Findings

`tooth_findings` are clinical facts over time: encounter + verified
practitioner + FDI tooth + condition-catalog reference + status
(`active/resolved`) + optional details. Surfaces live in normalized
`tooth_finding_surfaces` rows (unique per finding, queryable). History is
never destroyed — resolving marks status; multiple findings per tooth
coexist. No second diagnosis universe: findings reference the dental
condition catalog; encounter-level diagnoses use the generic diagnosis
model (P3-01), and dental-relevant codes (K02.9, K04.7, K05.30, K08.1)
exist there with ICD-10 mappings.

## Procedures: catalog vs records

`dental_procedures` answers "what exists" (code/display/specialty/
external-code, read-only). `dental_procedure_records` answers "what was
planned/performed for this patient" (encounter + practitioner + optional
plan-item link + tooth/surface + `planned → in_progress → completed`
lifecycle + notes). Content is immutable; only status transitions.

## Treatment plans

Plans belong to the patient with an optional encounter link, owned by a
verified practitioner. Lifecycle `draft → active → completed/cancelled`
(service-owned); items move `proposed → planned → in_progress →
completed/cancelled` through one transition table. Items change only while
the plan is a draft; activation requires ≥1 item; completion requires all
items terminal; cancel cascades to open items and is retry-safe. A plan is
clinical intent — not an estimate, not an invoice; no money fields exist.

## Consent

Minimum structured relationship: exactly one subject (plan XOR procedure
record, CHECK-enforced), consenter name/relation, optional document
reference (pointer only — signed bytes live in storage, never in the DB).
Lifecycle `pending → granted/declined`, with `withdrawn` from granted only.
Recorded by the provider present; actor + timestamp on every transition.

## Recalls and documents

Recalls are clinical review dates (`scheduled/completed/cancelled/missed`)
with patient/location scope — no audiences, templates, or automation.
`document_references` store metadata pointers (storage key, content type,
size, SHA) to objects behind the storage port: X-rays, scans, photos,
reports. No bytes, no public URLs.
