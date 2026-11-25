# P3.1 — Implementation report

**Verdict:** CONDITIONAL PASS  
**HEAD (unchanged):** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**Scope delivered:** P3.1-A (shell / design system / nav) + selected P3.1-B (dashboard, patients, schedule, reception).  
**Not claimed:** Full product redesign, onboarding completion, or browser E2E with live clinic accounts.

## What changed and why

### Design system / UI package

| Change | Why |
|--------|-----|
| `NavItem.group` optional | Grouped clinic IA without duplicate routes |
| `isNavActive` exported | Nested routes keep active highlight; `/` and `/portal` stay exact |
| `AppShell` clinic/portal variants | Distinct clinic sidebar vs patient “My Care” chrome |
| Mobile nav drawer + Escape/backdrop | Usable tablet/phone navigation |
| `.hos-page-header` / attention / quick-action classes | Replace inline styles; consistent page chrome |
| `ErrorState` uses `Button` | Align with primitives |

### Clinic workspace

| Change | Why |
|--------|-----|
| `lib/nav.ts` grouped labels + order | Overview → Patient Care → Clinical → Ops → Workspace |
| `shell.tsx` passes workspace, user, sign-out | Visible clinic context; consistent logout |
| Home dashboard attention metrics | Real `operations-dashboard` data when permitted |
| Permission-aware quick actions | Register / book / reception / walk-in / follow-ups |
| Patients `PageHeader`, compact table, `Textarea` | CRM clarity |
| Patient chart breadcrumbs + quick actions | Faster chart orientation |
| Schedule `PageHeader` | Consistent appointments chrome |
| Reception header buttons | Faster walk-in / calendar access |
| Portal `variant="portal"` brand “My Care” | Not an admin dashboard |

### DESIGN.md

Added §13 Application shells; renumbered subsequent sections. Documents clinic vs portal shell behavior.

## Components reused

`AppShell`, `PageHeader`, `Button`, `Card`, `Field`, `Select`, `Input`, `Textarea`, `Table`, `Alert`, `EmptyState`, `LoadingState`, `Status`, `Breadcrumbs`, `PatientIdentityHeader`, `MoneyDisplay` (unchanged usage).

## Components added

None as new primitives. Extended `NavItem` / `AppShell` API only.

## Routes affected

- `/` (dashboard)
- `/patients`, `/patients/[id]`
- `/schedule`, `/reception`
- All clinic pages via `shell.tsx`
- All portal pages via `portal/shell.tsx`

## Accessibility improvements

- Skip link retained
- `aria-expanded` / `aria-controls` on menu button
- Escape + backdrop dismiss for drawer
- Prefix-aware `aria-current="page"`
- Focus-visible styles unchanged from tokens
- Workspace/patient meta truncated with `title` for long names
- Menu button 44px min target

## Responsive behavior

- Clinic: drawer &lt;1024px; sticky sidebar ≥1024px
- Portal: top nav ≥768px; drawer &lt;768px; meta chips hidden on small screens
- `prefers-reduced-motion` disables drawer transition

## Known limitations

- Onboarding UX (workspace create, practitioner approve, invite accept, portal enroll) still missing — documented, not faked
- Follow-ups / operations / staff screens still use some raw selects (P3.1-C backlog)
- No Playwright browser evidence in this pass (build + unit only)
- SaaS subscription pages unchanged (payment freeze)
- Ophthalmology still discovery-only

## Backend dependencies (not implemented here)

- Workspace self-serve provisioning UI
- Practitioner approval UI
- Invitation acceptance UI
- Patient portal enrollment UI

## Test evidence

| Gate | Result |
|------|--------|
| `npm run typecheck -w @healthcare-os/ui` | Pass |
| `npm run test -w @healthcare-os/ui` | 17 pass |
| `npm run typecheck -w @healthcare-os/web` | Pass |
| `npm run test -w @healthcare-os/web` | 44 pass (5 files) |
| `npm run build -w @healthcare-os/web` | Pass (Next.js 16.4.6) |

## Browser verification

**Unverified** in this phase (no authenticated synthetic clinic session exercised in browser). Do not treat unit/build success as E2E workflow proof.

## Git preservation

- No commit, push, stash, reset, or clean
- No payment module edits
- No migrations created
- Working tree remains dirty with prior P1–P3.0 work plus P3.1 UI changes
