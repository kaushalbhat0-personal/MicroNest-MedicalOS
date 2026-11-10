# 06 — Reuse candidates (dental-erp @ 389d9841)

Classes: **A** reuse directly · **B** adapt · **C** recreate natively ·
**D** reference only · **E** reject. License for all code: MIT © 2026 Abinauv
Selvaraj — attribution + notice preservation required for any A/B reuse.

## RC-1 — Image viewer interaction vocabulary — **B (Adapt)**

- **Sources:** `components/imaging/image-viewer.tsx` (454 lines).
- **What:** zoom 0.25–5 (wheel+buttons+% label), rotate ±90°, flip H/V,
  brightness/contrast sliders, drag-pan when zoomed, fullscreen, prev/next,
  chrome auto-hide, keyboard shortcuts.
- **Dependencies:** react only (+ shadcn dialog/button, lucide icons, next-intl —
  all replaced by our primitives/tokens in adaptation).
- **Integration complexity:** medium. New viewer component in Dental specialty;
  image bytes via our StoragePort signed URLs (upload/download plumbing is
  prerequisite work); metadata from existing `document_references`.
- **License:** MIT attribution in adapted file header.
- **Risks:** missing loading/error states, unlabeled icon buttons, undisclosed
  shortcuts, no read-only prop — all must be fixed in adaptation (DESIGN.md
  §8/§11). PHI: titles/subtitles must stay minimal (§16).
- **Target:** `packages/ui` (dental viewer, specialty-first) + encounter/docs
  + patient workspace wiring.

## RC-2 — Image annotator (normalized coords, undo/redo, read-only) — **B (Adapt)**

- **Sources:** `components/imaging/image-annotator.tsx` (632 lines; exports
  `Annotation{id,type,points[0-1],color,lineWidth,text?}`).
- **What:** 6 tools, dual-canvas overlay, aspect-preserving fit, text flow,
  snapshot undo/redo stacks, ClearAll, `onSave`, `readOnly` mode.
- **Dependencies:** react + canvas 2D only. No external draw libs.
- **Integration complexity:** medium-high (canvas a11y alternative needed:
  annotation list with labels as the keyboard/SR path; UUID ids; tenant-scoped
  PUT endpoint; annotation storage design-gated — JSON column/sidecar on our
  document rows via migration).
- **License:** MIT attribution in adapted file header.
- **Risks:** mouse-only canvas (WCAG gap to close), `Math.random` ids,
  swallowed errors (route to our Alert/Toast patterns), annotation authz
  (author vs viewer roles).
- **Target:** same as RC-1 + backend annotations endpoint (new, additive).

## RC-3 — Before/after compare (slider + synced side-by-side) — **B (Adapt)**

- **Sources:** `components/imaging/image-compare.tsx` (247 lines).
- **What:** mode toggle, synchronized zoom/pan in side-by-side, `clipPath`
  slider, reset-on-open.
- **Dependencies:** react only.
- **Integration complexity:** low-medium once RC-1 exists (shares transform logic).
- **License:** MIT attribution.
- **Risks:** mouse-only slider (needs slider role + keyboard), no mobile
  stacking (stack vertically <lg), dates optional upstream — require them.
- **Target:** same viewer surface, launched from document pairs.

## RC-4 — Odontogram upgrades (legend, history, summary, read-only, responsive) — **C (Recreate natively)**

- **Sources (concept):** `components/dental-chart/dental-chart.tsx`,
  `components/imaging/dental-3d-viewer.tsx` (SVG arch idea only).
- **What:** tooltip/summary-count/history-list/legend ideas; U-arch layout idea.
- **Dependencies:** none transferable (fetch-coupled, Tailwind-v3 palette,
  next-intl, inconsistent cross-view colors, dead history, no a11y).
- **Integration complexity:** medium — extend `packages/ui/dental.tsx` (surface
  select on focus, legend fill+label+icon, resolved-history from our API,
  read-only prop, wrap/scroll rows, 44px targets).
- **License:** n/a (native work; note inspiration source in PR, no notice needed).
- **Risks:** clinical-semantics drift (5-surface set, bridge-as-condition,
  hidden MILD) — guarded by §05 dentist checklist.
- **Target:** `packages/ui/dental.tsx` + encounter Dental tab + patient Dental tab.

## RC-5 — Patient-workspace documents/imaging wiring — **B (Adapt, flow only)**

- **Sources (flow):** `app/(dashboard)/patients/[id]/page.tsx` (tabs + upload →
  viewer → annotate → compare + badges + lazy timeline).
- **What:** tab organization, thumbnail→viewer→annotator→compare chain,
  annotation badges, lazy timeline with filter.
- **Dependencies:** none transferred (page is fetch/Prisma-route coupled).
- **Integration complexity:** low (layout) once RC-1..3 + upload plumbing exist.
- **License:** flow ideas; any copied structure gets MIT header note.
- **Risks:** PHI-in-URL habits (`?patientId=`, file paths) must not transfer;
  use our route params + minimalផ្ទ display.
- **Target:** `apps/web/app/patients/[id]`, `apps/web/app/encounters/[id]` docs sections.

## RC-6 — Plan progress + consent-badge presentation — **D (Reference only)**

- **Sources:** `app/(dashboard)/treatments/plans/{page,[id]/page}.tsx`
  (`calculatePlanProgress`, badges, status-gated actions).
- **Why not code:** progress helper is trivial; costs are client-computed
  (architecturally forbidden here); no-debounce search; console-only errors;
  no-op Print.
- **Target:** our plan pages adopt the visual ideas (progress + counts, consent
  badge, grouped procedure picker) with server values + our states.

## RC-7 — Global search keyboard/debounce pattern — **B (Adapt)**

- **Sources:** `components/layout/global-search.tsx` (288 lines: 300ms debounce,
  min-2-chars, `/` shortcut, Arrow+Enter nav, category groups, footer hints).
- **Dependencies:** fetch endpoint (ours must be new, tenant-scoped, minimal-PHI).
- **Integration complexity:** low-medium (needs a scoped search API; DESIGN.md
  §22-adjacent — keep results to id/display/status).
- **License:** MIT attribution if structure followed closely.
- **Risks:** PHI minimization + audit of searches; backdrop/focus-trap discipline.
- **Target:** shared shell search (behind permission + tenant scope).

## RC-8 — Notification poll + optimistic read — **B (Adapt)**

- **Sources:** `components/layout/notification-tray.tsx` (60s poll, mark-read
  optimistic, type→icon map, `timeAgo`).
- **Dependencies:** notifications endpoint (ours: outbox/portal-backed when live).
- **Integration complexity:** low (blocked on provider wiring for real content).
- **License:** MIT attribution.
- **Risks:** silent-fail pattern must become visible-error per §11; entity
  navigation must respect authz (their `entityType/entityId` unused — wire
  properly or omit).
- **Target:** shared shell tray.

## RC-9 — Recall/lab/inventory/sterilization/comms/reporting concepts — **D (Reference only)**

- **Sources:** `app/api/cron/{recall,reminders,collections,inventory}/route.ts`,
  `lib/services/communication-triggers.service.ts`, `app/(dashboard)/{lab,inventory,
  sterilization,communications,reports}/**`, `components/ui/export-menu.tsx`.
- **Why not code:** Prisma cron routes, AI-coupled insights, custom gateway code —
  none transferable to our modular monolith.
- **Domain references worth keeping:** lab work-type list (12) + lab statuses (9),
  stock-alert threshold concept, sterilization log shape, recall-candidate signals
  (6+mo no-visit, incomplete plans, overdue follow-ups), export-menu UX.
- **Target:** future native modules (lab/sterilization post-scope; recall reminders
  with P8.1 provider; dentist-facing list APIs per §22).

## RC-10 — Everything backend/AI/payments/portal-server/auth — **E (Reject)**

- **Sources:** `prisma/schema.prisma`, all `app/api/**` routes, better-auth,
  `lib/ai/**` (16 skills + gateway + executors), `lib/payment-gateways/**`,
  `app/portal/**` server parts, `Hospital` tenancy, billing domain, MySQL
  specifics, CORS-`*`, `limit=100` PHI fetches, free-text teeth, client money math,
  no-op Print, dangling manifest PNGs.
- **Why:** architectural incompatibility (MySQL/Prisma/Next-routes vs our
  FastAPI/Postgres), authz bypass risk, clinical-safety risk (unedited costs,
  unvalidated teeth), unvalidated AI clinical surface, PCI-adjacent custom
  gateway code, redundant portal/billing/prescription domains.
- **Target:** none. Concepts from RC-9 only.

## Attribution ledger (for any future A/B work)

- Upstream: `abinauv/dental-erp`, MIT, Copyright (c) 2026 Abinauv Selvaraj.
- Each adapted file must retain: original MIT notice + copyright line + source
  path + HEAD SHA `389d9841` + "adapted for Healthcare OS" note.
- No third-party artwork/fonts cleared or needed (see `03-visual-assets-audit.md`).
- Transitive deps of candidates: react + canvas only (dialog/button/icons/i18n
  replaced by our system). No new dependencies permitted by this audit.
