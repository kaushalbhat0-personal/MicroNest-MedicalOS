# 01 — Repository map (dental-erp @ 389d9841)

External: https://github.com/abinauv/dental-erp · branch `main` ·
HEAD `389d984115a3b6e82161ffe6f17607d85a46669b` (2026-11-10).
`package.json`: name `dental-erp`, version `2.1.1`, private, engines node ^22/24.

## Architecture

Single-tenant-oriented **Next.js 16 + React 19 App Router** monolith.
Frontend pages, API routes (`app/api/**`), Prisma ORM over **MySQL**,
better-auth sessions, BullMQ/Redis queues, S3-compatible uploads, nodemailer,
fetch-based AI gateway (OpenRouter/Anthropic/Bedrock), custom
Razorpay/PhonePe/Paytm gateway code (no payment npm SDKs), next-intl i18n,
next-themes dark mode, TanStack Query, recharts, react-hook-form + zod.

Nothing here maps onto our FastAPI modular monolith + PostgreSQL. No server
code is reusable; only isolated client interaction patterns are candidates.

## Relevant directories and modules

| Path | What it is | Lines / notes |
|---|---|---|
| `components/dental-chart/dental-chart.tsx` | Fetch-driven chart (`{patientId}` → GET/POST `/api/dental-chart`) | 611 |
| `components/treatments/dental-chart.tsx` | Legacy prop-driven chart (`entries/onEntryCreate/onEntryUpdate/editable/selectedTeeth`, uses `lib/treatment-utils`) | 523 — duplicate, prefer the former as reference |
| `components/imaging/image-viewer.tsx` | Presentational viewer (props only) | 454 |
| `components/imaging/image-annotator.tsx` | Canvas annotator, exports `Annotation` | 632 |
| `components/imaging/image-compare.tsx` | Before/after compare | 247 |
| `components/imaging/dental-3d-viewer.tsx` | SVG U-arch viewer (mislabeled "3D") | 657 |
| `components/layout/dashboard-shell.tsx` | Shell: SidebarProvider + aside + Header + main + CommandBar/ChatWidget | 65 |
| `components/layout/sidebar.tsx` | Role-based nav, collapsible w-16/w-64 | 193 |
| `components/layout/mobile-sidebar.tsx` | Overlay panel, Esc/backdrop close | 129 |
| `components/layout/global-search.tsx` | Debounced `/api/search`, keyboard nav | 288 |
| `components/layout/notification-tray.tsx` | Poll + optimistic read | 220 |
| `components/layout/header.tsx`, `user-menu.tsx`, `theme-toggle.tsx`, `keyboard-shortcut-help.tsx`, `sidebar-context.tsx` | Chrome extras | — |
| `app/(dashboard)/patients/[id]/page.tsx` | 9-tab patient workspace incl. chart + documents wired to viewer/annotator/compare | ~1269 |
| `app/(dashboard)/treatments/plans/page.tsx` | Plan list w/ filters + pagination | 398 |
| `app/(dashboard)/treatments/plans/new/page.tsx` | Plan create (patient pick + procedure items) | 541 |
| `app/(dashboard)/treatments/plans/[id]/page.tsx` | Plan detail, transitions, consent dialogs | 551 |
| `app/(dashboard)/lab/**`, `inventory/**`, `sterilization/**`, `communications/**`, `reports/**` | Ops modules (real, Prisma-coupled) | — |
| `app/portal/**`, `components/portal/portal-shell.tsx`, `app/api/patient-portal/*` | Patient portal (OTP model) | — |
| `lib/ai/skills/*` (16 files), `lib/ai/{openrouter,providers/*,…}`, `app/api/ai/*` (16 routes), `components/ai/*` (11 files) | AI subsystem | Reject wholesale |
| `lib/payment-gateways/*`, `lib/services/{sms,email,template,communication-triggers}.service.ts` | Payments/comms | Reject wholesale |
| `prisma/schema.prisma` | ~2999 lines, MySQL, 70+ models, ~40 enums | Reject wholesale |
| `tests/components/*.test.tsx` (31 files), `TEST_PLAN.md` | Claims 4,398 Vitest + ~478 Playwright E2E; many `[ ]` unchecked (perf, a11y contrast, fresh-DB build, rollback, RTL, visual regression) | Treat counts as unverified |
| `public/manifest.json` | Sole tracked public file (PWA manifest) | 497 B |

## Technology and dependency notes (from `package.json`)

- `next ^16.4.5`, `react ^19.2.3`, `prisma 5.22.0`, `tailwindcss ^3.4.17`
  (+`tailwindcss-animate`), 17× `@radix-ui/*`, `lucide-react ^1.70.0`,
  `better-auth ^1.7.18` (README's "NextAuth v5" claim is stale),
  `next-intl ^4.13.4`, `bullmq`+`ioredis`, `@aws-sdk/client-s3`,
  `recharts`, `typescript` via `npm:@typescript/typescript6` (README's "TS 5" stale).
- No `openai` / Vercel `ai` SDK; no payment SDKs; no image-processing libs
  (annotator is raw canvas 2D).
- `next.config.js`: standalone output, `images.unoptimized`, serverActions 10mb,
  CORS `*` on `/api/:path*` (do not emulate), basic security headers.

## Key dental data shapes (for comparison only — do not import)

- `DentalChartEntry`: `toothNumber Int`, 5 booleans
  (mesial/distal/occlusal/buccal/lingual), `condition` enum (14 values),
  `severity`, `diagnosedDate/resolvedDate`.
- `TreatmentPlan`: `planNumber/title/status/estimatedCost/consentGiven`;
  items carry `toothNumbers` free-text + `estimatedCost` (client-editable).
- `Document`: `documentType` (XRAY/CT_SCAN/PHOTO/…), `annotations Json?`.
- Compare with ours: findings with 8 normalized surfaces + active/resolved-only
  lifecycle; plans clinical-only (no money); document metadata pointers only.
