# P3.1 — Design system audit

**Source of truth:** `DESIGN.md` + `packages/ui`.  
**Decision:** Extend the existing system; do **not** introduce a parallel design system or replace frameworks.

## What is already strong

| Layer | Status | Notes |
|-------|--------|-------|
| Tokens | Strong | Primitive → semantic; brand override only on `--hos-brand-*` |
| Contrast | Strong | Primary 5.1:1; muted/danger documented; focus ring defined |
| Typography | Strong | Scale + mono for IDs; system stack offline-safe |
| Primitives | Strong | Button, Field, Input, Select, Dialog, Tabs, Table, Status, Toast |
| Healthcare | Good | PatientIdentityHeader, MoneyDisplay, Odontogram, imaging viewer |
| Status mapping | Strong | Backend-authoritative via `status.ts` |

## Gaps to close in P3.1-A

1. **`NavItem`** — add optional `group` (and later `icon` if needed) so clinic IA can section without duplicate routes.
2. **`AppShell`** — sidebar + grouped nav on desktop; mobile drawer; workspace/user context; portal `variant` for distinct patient chrome; prefix-aware active route.
3. **`PageHeader`** — move inline styles to `.hos-page-header` token classes for consistency.
4. **`ErrorState`** — use `Button` primitive; keep retry affordance.
5. **Density** — clinic shell `data-density="compact"`; portal `comfortable` where practical.
6. **Active nav** — nested path highlighting without false positives (`/plans` vs `/dental/plans`, `/portal` home).

## Explicit non-goals this phase

- Dark mode (DESIGN §18 deferred).
- New visual identity / gradient marketing look.
- Replacing Radix or Tailwind.
- Inventing metrics widgets without backend data.
- Expanding SaaS payment UI beyond existing P2.5 surfaces.

## Token / DESIGN.md updates

Prefer implementation alignment over prose churn. Update `DESIGN.md` only when:

- Nav grouping / shell layout becomes a documented pattern, or
- Portal variant is an intentional product distinction.

Minimal DESIGN addition planned: note that clinic shell uses compact sidebar navigation and portal uses a calmer top-nav/`variant="portal"` presentation without changing authz semantics.

## Component reuse rules

- Import only from `@healthcare-os/ui` root.
- Improve existing components before adding new ones.
- No duplicate Button/Card/Alert in app folders.
- Prefer `Select`/`Input`/`Checkbox`/`Textarea` over raw hos-* class HTML when editing a screen.
