# P3.1 — Current-state UI/UX audit

**Date:** 2026-11-24  
**HEAD (pre-change):** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**Working tree:** Dirty (P1.x–P2.5 + P3.0 pilot readiness work preserved; no stash/reset).

## Verdict of baseline

The design system (`DESIGN.md` + `packages/ui`) is solid for tokens and primitives, but the clinic workspace chrome is still a flat top-nav link list without groups, mobile collapse, or workspace context. Page adoption of primitives is uneven. Patient portal reuses the same `AppShell` chrome as staff, so it feels like an admin tool.

## Evidence captured

| Area | Path(s) | Finding |
|------|---------|---------|
| Design source | `DESIGN.md` | Calm clinical instrument; token → primitive → pattern; WCAG AA; no decorative dashboards |
| Tokens | `packages/ui/tokens.css`, `theme.css` | Complete semantic palette; density/breakpoint tokens exist |
| Components | `packages/ui/{Button,fields,feedback,overlays,data,navigation,healthcare,dental}.tsx` | Broad kit; `ErrorState`/`Skeleton` underused in app |
| App CSS | `apps/web/app/globals.css` | Imports theme + components; legacy `.container`/`.card` aliases remain |
| Clinic shell | `apps/web/app/shell.tsx` | Permission-filtered nav; does **not** pass tenant/user/sign-out to `AppShell` |
| AppShell | `packages/ui/navigation.tsx` | Flat `NavItem { href, label }`; no groups/icons; exact path match only; no mobile drawer |
| Nav catalog | `apps/web/lib/nav.ts` | 16 flat items; permission rules present; tests in `nav.test.ts` |
| Home | `apps/web/app/page.tsx` | Tenant picker + ops teaser; not a “what needs attention today” dashboard |
| Patients | `apps/web/app/patients/page.tsx` | Search + register + CSV; no `PageHeader`; table lacks density |
| Patient chart | `apps/web/app/patients/[id]/page.tsx` | Strong tabs + timeline; no breadcrumbs; some raw selects |
| Schedule | `apps/web/app/schedule/page.tsx` | Day/week/month + book/reschedule; **missing `PageHeader`** |
| Reception | `apps/web/app/reception/page.tsx` | Queue board solid; header actions are plain links |
| Operations | `apps/web/app/operations/page.tsx` | Real location-scoped metrics API; denser than DESIGN prefers |
| Portal | `apps/web/app/portal/shell.tsx`, `lib/portal.ts` | Separate nav; same brand string “Healthcare OS”; passes tenant/user |
| Onboarding | signup/verify/login + admin | No guided workspace-create / practitioner-approve UI (P3.0 gap) |

## Information architecture (actual routes)

Implemented clinic routes used for nav (permission-gated):

- `/` Home
- `/operations` Operations dashboard
- `/reception` Reception queue
- `/follow-ups` Follow-ups
- `/patients`, `/patients/[id]` CRM
- `/schedule` Appointments calendar
- `/encounters` Clinical encounters
- `/dental/plans` Treatment plans
- `/billing/invoices` (+ estimates/payments/receipts/catalog sibling routes not in primary nav)
- `/inventory`, `/staff`, `/team`, `/admin`
- `/subscription`, `/plans` (SaaS catalog — frozen payment expansion)
- `/sessions`

Portal: `/portal/*` with fixed patient nav.

## Duplicate / inconsistent patterns

1. Raw `<select className="hos-input">` vs `Select` (follow-ups, operations, patient WhatsApp).
2. `PageHeader` present on reception/ops/follow-ups; absent on schedule and patient list.
3. Table `density="compact"` on reception/schedule; omitted on patients/follow-ups/ops.
4. Failures almost always `Alert`, rarely `ErrorState` + retry.
5. Clinic shell omits workspace identity; portal shell includes it.
6. Active nav is exact-match only → nested routes (e.g. `/patients/:id`) lose highlight.

## States coverage vs DESIGN §11

| State | Package | App usage |
|-------|---------|-----------|
| Loading | `LoadingState` | Common |
| Empty | `EmptyState` | Common |
| Error | `ErrorState` / `Alert` | Mostly `Alert` |
| Forbidden | — | Ad-hoc copy on ops |
| Not found | — | Sparse |
| Offline | — | Missing |
| Saving / saved | Button `loading` | Partial |

## Mobile / responsive

- Shell CSS (`components.css` ~L481–521): flex-wrap header only; **no** hamburger/drawer; **no** `@media` for nav.
- Long staff nav wraps into multi-row header on tablet/phone.
- Tables use horizontal scroll (`.hos-table-wrap`) — aligned with DESIGN §7.

## Security / authz UX (non-weakening)

- Nav filtered by server-derived permissions (`filterNavByPermissions`).
- Fail-soft to Home/Sessions when workspace context fails.
- Portal routes separate; portal-only users redirected from clinic home.
- Do **not** show inaccessible features as available.

## Strategic constraints (unchanged)

- SaaS payments frozen at P2.5; do not expand Razorpay.
- No ophthalmology clinical templates.
- No Docker; no commit/push; preserve dirty tree.
