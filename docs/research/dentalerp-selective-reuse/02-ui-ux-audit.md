# 02 — UI/UX audit (dental-erp @ 389d9841)

All paths verified with `-LiteralPath`. Behavior notes come from direct reads
of the listed components. Our DESIGN.md is authoritative; nothing below is a
copy instruction.

## A. Dental dashboard

- **Source:** `app/(dashboard)/dashboard/page.tsx`, `app/api/dashboard/stats/route.ts`,
  shell `components/layout/dashboard-shell.tsx` (65 lines: SidebarProvider,
  `aside hidden md:flex`, `main overflow-auto bg-muted/30 p-4 md:p-6` + Breadcrumb,
  plus CommandBar/ChatWidget).
- **Hierarchy:** sidebar sections by role (`getNavigationForRole`), header with
  search + notifications + user menu, main content cards, recharts widgets.
- **Density/cards:** card-heavy with metric tiles. Against DESIGN.md §1/§20
  ("dashboard-card overload", "decorative dashboards" are DON'Ts) this is the
  opposite of our direction — do not emulate the tile wall.
- **Quick actions / appointment / treatment visibility:** present (queue,
  today's appointments, plan progress summaries via `calculatePlanProgress`).
  The *idea* of a compact "today + open plans + due recalls" strip is worth
  adapting into our reception/schedule surfaces; the tile aesthetic is not.
- **Responsive:** shell collapses aside below `md`, mobile overlay sidebar.
  Tables use `overflow-x-auto min-w-[800px]` (consistent with our "scroll, never
  card-transform" rule — one of the few patterns already aligned).
- **States:** loading skeletons exist; errors often only `console.*` with no
  user-facing panel (plans list, plan detail actions, timeline) — below our
  §11 nine-states bar. Toasts via sonner/`use-toast` on some mutations only.

## B. Patient workspace

- **Source:** `app/(dashboard)/patients/[id]/page.tsx` (~1269 lines), 9 tabs:
  overview / dental-chart / timeline / documents / appointments / treatments /
  billing / forms / insurance. Chart tab embeds `DentalChart patientId`.
- **Header/identity:** header exists with booking quick action
  (`/appointments/new?patientId=` — PHI in URL; we must not copy that habit,
  DESIGN.md §16 forbids PHI in URLs).
- **Timeline:** lazy-loads on tab (`GET …/timeline?type=`), filter select,
  per-type icons/colors, skeletons vs empty states. Good organization; adapt the
  lazy-tab + filter idea behind our encounter/note/observation projections.
- **Documents:** upload (`FormData{file,documentType,description}`, accept
  jpg/png/gif/webp/pdf/doc/docx) → thumbnail grid → `ImageViewer` (with
  `onAnnotate`/`onCompare`) → `ImageAnnotator` (save → PUT annotations) →
  compare-mode checkbox (images only, sliding window of max 2) →
  `ImageCompare`. Annotation count badges. This end-to-end wiring is the best
  patient-workspace idea in the repo — adapt the *flow*, not the code.
- **Chart/treatment placement:** chart is one tab among nine; treatments and
  billing adjacent. Reasonable; our patient workspace
  (`apps/web/app/patients/[id]/page.tsx`: Overview/Encounters/Dental/Billing)
  is thinner — consider a documents/imaging section and timeline affordance
  once the backend exists (no new entities needed: our `document_references`
  already model the metadata).
- **Actions/confirmations:** delete uses confirm dialog; consent uses dialogs;
  destructive discipline is roughly present but ad-hoc.

## C. Dental chart

Two implementations (a smell — duplicated chart code):

| | `components/dental-chart/dental-chart.tsx` (611) | `components/treatments/dental-chart.tsx` (523, legacy) |
|---|---|---|
| Data | Fetch-driven, `{patientId}` only | Prop-driven (`entries/onEntryCreate/onEntryUpdate/editable/selectedTeeth`) |
| Reference value | Higher (self-contained) | Lower (coupled to `lib/treatment-utils`) |

- **FDI/orientation:** permanent only, 32 teeth, midline-correct order
  (`UPPER_RIGHT 18→11`, `UPPER_LEFT 21→28`, `LOWER_LEFT 31→38`,
  `LOWER_RIGHT 48→41`); quadrant labels q1/q2/q4/q3 mirrored patient view —
  correct. **No primary dentition** (51–85 absent). Same limitation as ours.
- **Representation:** per-tooth `button` with condition fill; surface involvement
  shown as a single yellow dot if any of 5 surfaces set (mesial/distal/occlusal/
  buccal/lingual — no incisal; `occlusal` reused for anteriors).
- **Colors/legend:** 12-condition Tailwind palette (e.g. CARIES red-500, FILLED
  blue-500, CROWN yellow-500). **Inconsistent with `dental-3d-viewer.tsx`**
  (CROWN purple, IMPLANT cyan, ROOT_CANAL orange there) — same patient renders
  different colors per view. Also color-only meaning in places; DESIGN.md §2/§14
  requires fill + label + icon. Our token states (finding/planned/completed/
  selected) are the model to keep.
- **Selection/editing:** click → Dialog (condition Select, severity Select,
  5 surface Checkboxes, notes Textarea, Save → POST + refetch). No delete/
  resolve affordance in the dialog; no undo; no zoom/pan.
- **Severity/notes:** MILD/MODERATE/SEVERE; **tooltip hides MILD** (lossy).
- **History:** history list UI exists but is **dead** — fetch filters
  `isActive=true`, so `resolvedDate` rows never arrive. Ours (active→resolved
  with `resolve_finding`) actually has the lifecycle; their UI doesn't display it.
- **Read-only:** none — always editable. Ours needs finalized/portal read-only.
- **Keyboard/SR:** tooth buttons have focus ring but **no `aria-label`**
  (10px number text, contrast risk); no arrow-key grid; SVG `<g>` teeth in the
  3D viewer have no role/tabIndex/keyboard handler at all. Our roving-tabindex
  odontogram (`packages/ui/dental.tsx`) is already ahead — keep and extend it.
- **Responsive:** `w-10 h-14 gap-1 flex` with no wrap/scroll — overflows on
  mobile. Ours must wrap/scroll per DESIGN.md §7.

Useful pattern to adapt: Tooltip + summary cards (present/caries/filled/missing
counts) + history list — rebuilt with our tokens, real resolved-history data,
and keyboard support. Belongs in the **Dental specialty**, not the shared system.

## D. Imaging workspace (highest-value section)

- **Viewer** (`image-viewer.tsx`, 454): zoom 0.25–5 (wheel ±0.1, buttons ±0.25,
  % label), rotate ±90°, flip H/V, brightness/contrast 0–200 sliders, drag-pan
  when zoom>1, fullscreen API, prev/next with `onIndexChange`, chrome
  auto-hide on canvas click, keyboard (`+/-/r/0/arrows/f`). Pure CSS transform —
  adjustments are **projection-only, never persisted** (correct instinct).
  Gaps: no loading/error states, raw icon buttons without `aria-label`s,
  shortcuts undisclosed in UI, no read-only prop (toolbar always on).
- **Annotator** (`image-annotator.tsx`, 632): 6 tools
  (freehand/line/arrow/circle/rectangle/text), 7 colors, width 1–10, dual canvas
  (base + in-progress overlay) sized to container preserving aspect, text popup
  (Enter/blur submit, Esc cancel), undo/redo stacks (buttons + Ctrl+Z/Y),
  ClearAll, Save → `onSave(annotations)`, `readOnly` hides chrome and disables
  drawing. **Normalized 0–1 coordinates** — resolution-independent, the right
  call. Persisted as `Document.annotations Json`. Gaps: canvas has no keyboard
  alternative, color dots lack labels, `generateId` uses `Math.random`
  (collision-prone — use UUIDs in ours), errors swallowed for parent handling.
- **Compare** (`image-compare.tsx`, 247): side-by-side (synchronized zoom/pan)
  + slider (`clipPath` handle) modes; resets on open. Gaps: mouse-only slider
  (no slider role/keyboard), no mobile stacking, no loading states.
- **Metadata/dates:** before/after carry `{src,title,date?}` — keep visible
  dates in our adaptation (clinical comparison needs them).

Why useful: we have **no viewer at all** (metadata pointers only). The toolbar
vocabulary, normalized-coordinate annotations, undo/redo, read-only mode, and
the two compare modes are exactly the interaction language to adapt onto our
tokens, storage-backed bytes, and tenant-scoped APIs. Belongs in Dental
specialty first; promote a generic viewer primitive to shared only if a second
specialty needs it.

## E. Treatment plans

- **List** (`plans/page.tsx`, 398): search + status/consent filters + pagination
  (`page/limit/total/totalPages`), table Plan/Patient/Procedures/Progress
  (`calculatePlanProgress`)/Cost (`formatCurrency`)/Status+consent badge,
  actions View/Edit (hidden when COMPLETED/CANCELLED — correct gating).
  **No search debounce** (fetch per keystroke) — fix in adaptation.
- **Create** (`new/page.tsx`, 541): `?patientId=` preselect, parallel
  patient/procedure fetch, client-side patient filter (top-10 slice),
  procedures grouped by category, items with free-text `toothNumbers`,
  `estimatedCost` defaulting to `basePrice` but freely editable,
  `calculateTotalCost` reduce displayed and POSTed. **Client-side money math +
  free-text teeth + `limit=100` PHI over-fetch** — all three are anti-patterns
  for us (server-authoritative money, validated FDI, minimal PHI).
- **Detail** (`[id]/page.tsx`, 551): status-driven actions
  (DRAFT→Propose, PROPOSED+!consent→RecordConsent, ACCEPTED→Start,
  IN_PROGRESS item starts link to treatment create), progress + COMPLETED/total,
  server `estimatedCost` display, consent + cancel dialogs, Print button that is
  a **no-op** (dead affordance — do not copy). Errors `console`-only on actions.
- **Presentation ideas worth adapting:** progress bar + counts, consent badge,
  status-gated actions, item→treatment deep link concept (ours: plan-item ↔
  procedure-record linkage, currently manual — see §05 checklist).
  Everything monetary must be re-thought server-side.

## F. Staff-facing experience

- **Roles:** sidebar nav per role (`getNavigationForRole`); role-appropriate
  sections exist. No deeper role-workflow modeling found (no dentist vs
  receptionist vs assistant swimlanes in code — pages are shared with nav
  filtering).
- **Dentist:** chart + plans + imaging wiring serve the dentist flow best.
- **Reception:** appointments queue/waitlist pages + check-in/out routes exist;
  ours (`reception/page.tsx` today's arrivals + check-in) is comparable.
- **Assistant:** sterilization logs/instruments pages exist (concept reference).
- **Mobile/tablet:** mobile overlay sidebar (no focus trap/`aria-modal` —
  fix in adaptation); chart row overflows on small screens; compare view
  squishes. Our tablet chair-side story (DESIGN.md §7: single-column,
  touch-first, 44px targets) is not answered by their code — adaptation must
  include wrap/scroll chart, stacked compare, 44px teeth targets.

## Per-pattern placement

- Shared design system candidates: viewer chrome pattern (later, if generalized),
  search keyboard/debounce micro-pattern, notification poll+optimistic-read
  micro-pattern, skeleton/empty-state discipline (ours already standardizes this).
- Dental specialty: odontogram upgrades, imaging viewer/annotator/compare,
  plan progress/consent presentation, patient-workspace documents/imaging section.
