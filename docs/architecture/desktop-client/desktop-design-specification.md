# Desktop UX design specification (Phase 1.1)

**Brand / system source:** root `DESIGN.md` + `packages/ui` tokens.  
**Target:** WCAG 2.2 AA.  
**Feel:** Professional clinical workstation software — not a browser page framed in a window.

---

## 1. Principles (desktop-specific)

1. Preserve Healthcare OS tokens, status mapping, and backend-authoritative values.  
2. Prefer **multi-pane** layouts at ≥1280px (list | detail | context).  
3. Default density: **Compact** (staff). Clinical tables: **Clinical-Dense**.  
4. Keyboard-first: shortcuts for search, new appointment, save note (define in implementation).  
5. No marketing heroes, gradient chrome, or dashboard-card spam.  
6. Online-first: clear offline blocking state (not a silent stale UI).

---

## 2. Application chrome

| Element | Spec |
|---------|------|
| **Sidebar** | ~240px; grouped (Overview / Patient Care / Clinical / Clinic Operations / Workspace); active state; collapse to icons ≤1024px optional |
| **Top toolbar** | 48–56px; left: clinic name + location selector; center/right: global search; notifications bell (future placeholder disabled); user avatar menu |
| **Workspace switcher** | Tenant list from `/auth/me`; switching reloads permission-filtered nav |
| **User profile menu** | Profile (future), Sessions, Sign out |
| **Search** | Patient-first typeahead (API-backed); result opens Patient 360 |
| **Notifications** | **future** — reserve icon; do not fake unread counts |
| **Breadcrumbs** | Detail pages only; use `Breadcrumbs` from `@healthcare-os/ui` |
| **Page headers** | `PageHeader` title + primary/secondary actions; avoid duplicate titles |

---

## 3. Patterns

| Pattern | Spec |
|---------|------|
| **Tables** | TanStack for server-filtered lists; horizontal scroll below `lg`; never cardify clinical tables |
| **Filters** | Inline filter bar above table; persist per-session only in v1 |
| **Forms** | DESIGN §12 — label above, error summary, pending save |
| **Dialogs** | Radix Dialog; destructive confirmations explicit |
| **Patient profile** | Identity header sticky (name + ID + context); tabbed body |
| **Appointment calendar** | Day/week primary; month secondary; drag-reschedule only if API supports (match web) |
| **Clinical workspace** | Left patient context, center documentation tabs, right optional orders/history at wide widths |
| **Empty / error / forbidden** | Use `EmptyState` / `ErrorState` / no-permission copy — distinguish all three |

---

## 4. Responsive desktop resolutions

| Width | Behavior |
|-------|----------|
| ≥1536 | Multi-pane clinical + optional third context column |
| 1280–1535 | Sidebar + main; secondary panels as tabs |
| 1024–1279 | Sidebar persistent; reduce padding |
| &lt;1024 | Drawer nav (same as web clinic); single column — tablet chair-side |

Playwright already uses 1280 / 1440 — reuse as visual baselines for desktop SPA.

---

## 5. Role skins (navigation only)

Same components; different default home and pinned items (see role-workflow-matrix). Do **not** fork visual themes per role.

---

## 6. Motion & accessibility

- 150/250ms ease-out; honor `prefers-reduced-motion`.  
- Visible focus rings from tokens.  
- Skip link to main content.  
- Min 44px targets on primary actions.  
- No color-only status (use `Status` component).

---

## 7. What not to change without ADR

- Primary `#2563eb` and semantic status tones  
- Server-authoritative money/status  
- Portal “My Care” branding (patient app only)
