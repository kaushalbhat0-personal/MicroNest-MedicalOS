# DentalERP Selective-Reuse Research — README

## Executive summary

External reference: **https://github.com/abinauv/dental-erp** — inspected at
`main` HEAD **`389d984115a3b6e82161ffe6f17607d85a46669b`**
(2026-11-10, "Merge pull request #83 from abinauv/fix/unused-code-nocheck").
License file: **MIT, Copyright (c) 2026 Abinauv Selvaraj** (verified verbatim header).

**Verdict: ADAPT selectively, REUSE almost nothing verbatim, RECREATE the rest natively.**

Our Healthcare OS Dental specialty is already strong where it matters most:
tenant-scoped findings → plans → procedure records → consents → recalls →
document-reference metadata, all service-enforced, audited with opaque IDs,
tested (`tests/api/test_dental_api.py`, `tests/isolation/test_clinical_isolation.py`,
portal projections). DentalERP does not beat us on clinical safety, tenancy,
or backend discipline — it is a Next.js + Prisma/MySQL single-clinic app with
client-side money math, free-text teeth, and PHI-in-URL patterns we must not import.

What DentalERP is genuinely useful for is **frontend interaction patterns**:

1. **Imaging viewer/annotator/compare** (`components/imaging/*`, ~1.3k lines) —
   the single highest-value reference. We have NO imaging viewer (only
   `document_references` metadata pointers). Its zoom/pan/rotate/flip/
   brightness-contrast viewer, normalized-coordinate canvas annotator with
   undo/redo + read-only mode, and synchronized before/after compare are the
   right interaction vocabulary. **Adapt** (rewrite onto our tokens/API/storage).
2. **Patient workspace organization** — 9-tab chart
   (`app/(dashboard)/patients/[id]/page.tsx`) with lazy timeline, document
   upload → viewer → annotate → compare wiring, and annotation badges.
   Valuable as layout thinking; **adapt** to our patient-banner → encounter-bar
   → tabs architecture, not copy.
3. **Plan list/detail presentation** — progress bars, consent badges, status
   gating, cost display. Ideas only: their costs are client-computed and
   editable; ours must stay server-authoritative. **Reference only.**
4. **Global search keyboard UX + notification polling** — good micro-patterns
   (debounced search, `/` shortcut, 60s poll + optimistic read). **Adapt**
   behind our tenant-scoped APIs with PHI-minimal results.
5. **Recall/lab/inventory/sterilization/communications concepts** — real
   implementations exist there, but they are Prisma-coupled cron/API code.
   **Reference only** (workflow ideas for our future modules); no code reuse.

**Explicitly rejected:** Prisma schema, MySQL code, tenancy model, auth/session
(better-auth), all Next.js API routes, authorization logic, billing domain,
custom payment gateways, all 16 AI skills + AI API routes, portal backend,
client-side cost computation, free-text tooth entry.

**Visual assets:** there is nothing to reuse. The repo contains exactly one
tracked image file (`app/icon.svg`, original tooth logo) plus a PWA manifest
referencing two PNGs that are not committed. All dental imagery is code-drawn
SVG/canvas + lucide-react icons. Our odontogram artwork must be recreated
natively under our design system.

## Audit scope

- External HEAD recorded before work: `389d9841` (via `git ls-remote` + clone).
- All "starting point" paths from the brief verified to exist (two apparent
  misses were a PowerShell `[id]`-wildcard artifact; re-checked with
  `-LiteralPath` — all 18 paths exist).
- Our baseline: branch `main`, HEAD `efefb0a3…`, DESIGN.md (source of truth),
  `backend/app/modules/dental/*`, `backend/app/api/v1/dental.py`,
  `packages/ui/dental.tsx`, `apps/web/app/dental|patients|encounters|portal|reception`,
  `docs/pilots/dental-workflow-discovery.md`, dental + isolation + portal tests.
- Comparison map used throughout: DentalERP capability → our capability →
  actual gap → proposed enhancement (see `04-functional-gap-analysis.md`).
- No code, asset, or schema was copied. Audit-only; see "Git preservation"
  in the closing report (turn output).

## Overall recommendation

| # | Enhancement (for our OS) | Class | Value |
|---|---|---|---|
| 1 | Imaging viewer (zoom/pan/rotate/flip/B-C, keyboard) | Adapt | Highest — fills a missing module |
| 2 | Image annotation (normalized coords, undo/redo, read-only) | Adapt | Highest — fills a missing module |
| 3 | Before/after compare (slider + synced side-by-side) | Adapt | High |
| 4 | Odontogram upgrades (5-surface dots → full 8-surface select, legend, history-that-works, read-only mode, responsive wrap) | Recreate natively | High |
| 5 | Patient workspace tab/thumbnail/annotation-badge organization | Adapt | Medium-high |
| 6 | Plan progress + consent-badge presentation | Reference only | Medium |
| 7 | Global-search keyboard/debounce micro-pattern | Adapt | Medium |
| 8 | Recall-reminder / lab / inventory-alert / sterilization concepts | Reference only | Later |
| 9 | Everything backend / AI / payments / portal-server | Reject | — |

Details: `06-reuse-candidates.md` (classification per candidate),
`07-prioritized-backlog.md` (ordering), `08-integration-plan.md` (sequence).

## Documents in this package

- `01-repository-map.md` — architecture, modules, tech/dependency notes.
- `02-ui-ux-audit.md` — dashboard, patient workspace, chart, imaging, plans, responsive/a11y.
- `03-visual-assets-audit.md` — asset inventory, provenance, reuse calls.
- `04-functional-gap-analysis.md` — feature-by-feature comparison with actual gaps.
- `05-clinical-workflow-review.md` — FDI/chart/imaging/lifecycle review + dentist checklist.
- `06-reuse-candidates.md` — A/B/C/D/E per candidate with deps, risks, targets.
- `07-prioritized-backlog.md` — must-have / high-value / later / reject.
- `08-integration-plan.md` — smallest sensible sequence, gates, sign-offs.
