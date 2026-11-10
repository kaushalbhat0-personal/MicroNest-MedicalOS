# 08 — Implementation Plan (for D2, gated)

## P0 — Clinical sign-off gate (blocks schema work)

Dentist walkthrough: audit §05 checklist + `09-…​` Q1–Q8. Approve tool
vocabulary on mock data (RC-2 demo, no persistence). No migration, no
endpoint, no annotator code until P0 is recorded. (Reaffirms
dentalerp `08-integration-plan` Step 0.)

## P1 — Geometry library + pure tests

New `packages/ui/annotation-geometry.ts` (pure functions, §03 math) +
zero-dep `node --test` matrix (§07-§1). Independent of all clinical
decisions except per-mille storage (T-decision, safe default). Gate:
full 16-combo + round-trip suite green.

## P2 — Backend: migration + endpoints + API tests

Additive migration (`image_annotation_sets/items/revisions`, §04-§2;
follow `0017` conventions: additive-only, documented downgrade, RLS-safe).
Endpoints per §05-§5 with `DENTAL_READ`/`DENTAL_RECORD`, `match_tenant`,
`_encounter_in_scope`, `_audit`, `expected_version` 409s, idempotency.
Gate: §07-§2/3/4 suites green incl. D1b-style probes; `ruff`, `mypy`,
contract tests unaffected.

## P3 — Frontend: annotation mode + overlay + tests

Mode toggle in DocsTab viewer section (DENTAL_RECORD only), SVG overlay
sharing the viewer transform (§03-§3), list-driven keyboard/SR path,
undo/redo command stack, save/finalize/discard, overlay toggle, draft
watermark. `ClinicalImageViewer` itself unchanged (read-only default).
Gate: 30-test D1c suite still green + new vitest files (§07-§5 jsdom
part) + `next build` + token checks.

## P4 — Hardening and release

Real-browser responsive/keyboard pass (320/768/1440), audit-event review,
portal-exclusion re-verified, retention note filed (Q5), dentist
chair-side sign-off. Gate: DESIGN.md §21 QA list.

## Dependencies

P1 → P3 (geometry before overlay); P0 → P2 (sign-off before schema);
P2 → P3 (endpoints before UI wiring); D1/D1b/D1c unchanged throughout.

## Explicit exclusions (not in D2 first release)

Freehand/arrows/ellipse, color pickers, measurement rulers, annotated
compare, export/flatten/print, portal visibility, finding auto-creation,
real-time collaboration, autosave, annotation of non-image documents,
primary-dentition changes, any DentalERP code or dependency.
