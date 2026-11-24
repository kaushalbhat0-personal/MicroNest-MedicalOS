# Healthcare OS Design System (DESIGN.md)

**Status:** source of truth for Penpot design work and `packages/ui` implementation.
**Scope:** provider app, future patient portal, platform admin, white-label tenants.
**Non-goals:** copying any product's visual identity; decorative marketing UI.

## 1. Philosophy

Calm, trustworthy, precise clinical instrument. Dense where scanning matters,
spacious where cognition matters. Predictable, keyboard-first, accessible.
A system a clinician can trust with a real patient's care.

Avoid: gradients, glassmorphism, neon, shadow-heavy chrome, hero sections
inside operational screens, dashboard-card overload, decorative animation,
visual noise, illustrations in workflows.

## 2. Principles

1. Clinical safety over visual cleverness.
2. The patient is always unambiguous: name + ID + context on every chart surface.
3. No color-only meaning — every state pairs color + text (+ icon where scanning matters).
4. The UI displays server-authoritative values; it never computes money, status, or balances.
5. One system: tokens → primitives → patterns → healthcare → workspaces. No forks.
6. Accessibility is a constraint, not a feature (WCAG 2.2 AA).
7. Appearance may white-label; behavior and authorization never change.

## 3. Tokens

`packages/ui/tokens.css` is the single source of truth.
Layers: primitive (`--hos-blue-600`) → semantic (`--hos-primary`) →
component (implicit via classes). Tenant override allowed ONLY on
`--hos-brand-*` primitives. Everything else is immutable.

Key values: primary #2563eb (white text 5.1:1), success #15803d,
warning text #8a5a00 on #fef3c7, danger #dc2626, info #1d4ed8,
focus ring #2563eb 2px + 2px offset, border-strong #64748b (decorative
`#e2e8f0` fails non-text contrast — never use it for meaning).
Muted #64748b and danger small text must be re-verified in Penpot.

Tailwind v4 maps these via `@theme inline` (`packages/ui/theme.css`), so
utilities reference live variables and white-label works without rebuild.
Lint forbids raw hex and non-token colors in app code.

## 4. Typography

System stack default (offline-safe for on-prem deployments):
`ui-sans-serif, system-ui, …`; mono stack for identifiers. Optional
webfont enhancement (Lexend/Source Sans 3) only where network allows.
Scale: Display 30/36 · H1 24/32 · H2 20/28 · H3 16/24 · Body 15–16/24 ·
Small 13–14/20 · Caption 12/16 · Label 13–14/20 600. Tabular numerals
for money, dosage, identifiers, dates. Min body 13px (dense only).

## 5. Spacing / Density / Radius / Elevation

4px base (4/8/12/16/24/32/48). Densities: Comfortable (forms, portal),
Compact (staff default), Clinical-Dense (chart tables, 36px rows).
Radius: control 8, card 12, modal 16; pill reserved for badges/tags.
Elevation: border-first; subtle hover, raised dialog, overlay popover.

## 6. Motion

150ms micro / 250ms standard, ease-out. `prefers-reduced-motion` disables
non-essential motion. Never animate layout in clinical flows.

## 7. Responsive

Breakpoints 640 / 768 / 1024 / 1280 / 1536. Desktop = multi-pane
workstations; tablet 768–1024 = single-column chair-side, touch-first;
mobile = quick actions + future portal. Tables scroll horizontally below
`lg` — never card-transform clinical tables (comparison must survive).

## 8. Accessibility (WCAG 2.2 AA)

Native semantics; visible `:focus-visible` ring + offset; error summary
with focus-move + retained inline errors; `role=alert` errors,
`role=status` success, `aria-live` loading; `scope` + caption tables;
44px minimum targets; contrast-verified pairs; no color-only states;
skip-link + landmarks; keyboard-complete flows.

## 9. Component architecture

`packages/ui/`: `tokens.css`, `theme.css`, `components.css`,
`status.ts`, primitives (`Button`, `fields`, `feedback`, `overlays`,
`data`, `navigation`), healthcare (`healthcare.tsx`, `dental.tsx`),
`Toast`, barrel `index.ts`. App code imports only from
`@healthcare-os/ui` root. Radix supplies behavior for Dialog, Popover,
Tooltip, DropdownMenu, Tabs, Select(rich). TanStack Table only for
server-filtered lists (charge master, queues, audit).

## 10. Backend-authoritative status

`Status` maps backend strings to (tone, label): appointments,
encounters, notes, prescriptions, invoices, payments, plans, consent,
recalls, credit notes (see `status.ts`). Unknown → neutral "Unknown".
Never invent frontend states; never render Edit on immutable records
(render the correction affordance instead).

## 11. States

Every surface handles: loading (skeleton + `aria-busy`), empty (title +
action), error (alert + retry), forbidden (no-permission copy), not found,
offline, saving (pending button), saved (status), partial success
(itemized). Distinguish no-data vs failed-load vs no-permission.

## 12. Forms

Label above, `*` + required, helper below, error below linked via
`aria-describedby` + `aria-invalid`; summary with focus on submit failure;
validate on submit + touched; server errors in summary; never
placeholder-only labels; pending + unsaved indicators; read-only vs
disabled distinguished.

## 13. Application shells

Clinic workspace (`AppShell` `variant="clinic"`): compact density, grouped
sidebar navigation (Overview / Patient Care / Clinical / Clinic Operations /
Workspace), sticky header with workspace + signed-in identity, mobile drawer
with Escape/backdrop dismiss. Permission-aware nav remains server-gated.

Patient portal (`variant="portal"`): brand “My Care”, comfortable density,
top nav on tablet+, drawer on small screens. Must not look like clinic admin.

`PageHeader` uses `.hos-page-header` token classes. Active routes use
prefix-aware matching (`isNavActive`) with exact match for `/` and `/portal`.

## 14. Clinical workspace

Persistent patient banner → encounter context bar → tabs
(SOAP/vitals/dx/Rx/dental/docs) → sticky sign/close actions. Close =
explicit checklist, waivers never pre-checked. Finalized = read-only +
amend affordance with visible supersede chain.

## 15. Dental

Odontogram = SVG projection of finding rows (FDI 11–48 permanent;
primary dentition deferred). States via fill + label + icon
(existing/planned/completed/selected); keyboard roving grid; surface
select on tooth focus. Projection only — never stored pixels.

## 16. Billing

Display server values only. Money: right-aligned tabular + currency.
Draft watermark vs issued lock. Balance widget (grand/allocated/
outstanding), credit badge, lineage (source estimate, FY/doc-number).
Void/refund/reversal require explicit reason + confirmation.

## 17. Sensitive data

Mask phones/identifiers with reveal; no PHI in URLs, titles, toasts,
or logs; truncated document names; breadcrumbs use "Patient chart +
ID"; search shows minimal fields. Frontend masking is convenience,
never security (backend enforces).

## 18. White-label

Customizable: brand primary/hover/active, accent, logo, favicon,
approved font choice, portal theme, email/PDF skin. Immutable: contrast
floor, focus, status semantics, authz, destructive protections,
interaction semantics. Overrides apply to `--hos-brand-*` only.

## 19. Dark mode

Deferred: needs clinical-readability validation; white-label matrix
explosion; zero current demand. Semantic tokens keep it a future theme.

## 20. Penpot handoff

Pages: 00-Foundation, 10-Primitives, 20-Patterns, 30-Doctor,
31-Reception, 32-Accountant, 33-Admin, 40-Tablet, 41-Mobile,
50-Dental, 60-Billing, 90-Portal-Future (empty), 99-Playground.
Libraries: color, typography, components, icons, patterns.
Naming: `Hos/[Layer]/[Component]/[Variant]`. Variants: variant, size,
state, density, icon. Tokens map 1:1 to CSS names. Workflow: connect →
read-only audit → tokens → primitives → patterns → screens → MCP audit
→ iterate. No writes without human approval.

## 21. Do / Don't

DO: semantic tokens; explicit patient identity; tabular money; obvious
primary actions; whitespace around clinical content; keyboard flows;
consistent density; visible focus. DON'T: color-only states; hidden
critical info; animation; arbitrary colors; tiny clinical text;
decorative dashboards; white-label contrast violations; client-side
financial math.

## 22. QA gate

Penpot-approved · tokens/components only · obvious primary action ·
protected destructive/finalizing actions · WCAG AA + keyboard + focus +
semantics · responsive trio · all nine states · no PHI leaks ·
tenant/location correct · type-safe · tested.

## 23. Open decisions

Webfont offline policy detail; recall-board/consent-list/receipt-list/
audit-facet APIs; notification channels/templates; branding asset
pipeline; demographics depth + dedup rules; support-access UX; MFA UX;
print/PDF; i18n/RTL.
