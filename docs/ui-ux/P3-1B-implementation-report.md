# P3.1-B — Implementation report

**Verdict:** CONDITIONAL PASS  
**HEAD (unchanged):** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**Migrations:** none  
**Payment / backend rules:** unchanged

## Screens and components changed

| Area | Files |
|------|-------|
| Dashboard | `apps/web/app/page.tsx` |
| Patient directory | `apps/web/app/patients/page.tsx` |
| Patient 360° | `apps/web/app/patients/[id]/page.tsx` |
| Appointments | `apps/web/app/schedule/page.tsx` |
| Reception | `apps/web/app/reception/page.tsx` |
| Shared CSS | `packages/ui/components.css` (filter/overview/summary/truncate/row-actions) |

**Reused:** `PageHeader`, `Card`, `Button`, `Field`, `Select`, `Checkbox`, `ConfirmDialog`, `ErrorState`, `EmptyState`, `LoadingState`, `Table`, `Status`, `MoneyDisplay`, `PatientIdentityHeader`, `Breadcrumbs`, `Tabs`.

**No new UI library.** No duplicate primitives.

## Interaction improvements

### Dashboard
- Attention-first layout; workspace card moved below.
- Today’s appointments table from real `todays_appointments`.
- Separate due vs overdue follow-up cards; outstanding invoices + `MoneyDisplay`.
- Refresh + `ErrorState` retry; clearer service-day period copy.
- Quick actions remain permission-aware.

### Patient directory
- Active/inactive/all client filter on server-returned rows (no unsupported API filters).
- Result count; Chart action; truncated long names.
- Register → navigates to new chart after server success.
- CSV import collapsed by default.

### Patient 360°
- Tabs: Overview · Timeline · Clinical · Care · Billing · Details.
- Overview attention cards: next appointment, last visit, balance, follow-ups.
- Clinical merges appointments, encounters, plans, recalls.
- WhatsApp uses `Select` + `Checkbox`; deactivate uses `ConfirmDialog`.
- Book deep-links `/schedule?patient=…`.
- Compact tables; chronology concentrated on Timeline.

### Appointments
- Patient + practitioner columns; ghost time opens detail dialog.
- Empty state Book / Walk-in CTAs.
- Cancel confirmation; booking `loading` until server confirms.
- Prefill patient from `?patient=`; walk-in `Checkbox`.
- Explicit booking steps copy; no invented availability.

### Reception
- Summary strip: waiting, checked in, next token, completed.
- Refresh; ErrorState retry; walk-in empty CTA.
- Completed/no-shows hidden until expanded.
- Server tokens only; status changes await API then reload (no optimistic queue numbers).

## Accessibility

- Confirm dialogs for destructive cancel/deactivate.
- Status announcements on counts (`role="status"`).
- Focus-visible tokens unchanged.
- Truncation with `title` for long names.
- Compact tables keep horizontal scroll pattern from design system.

## Responsive

- Filter/overview/summary grids use `auto-fit` minmax.
- Row actions wrap; truncate caps name width.
- Shell drawer from P3.1-A unchanged.

## Backend dependencies / limitations documented

- Directory has no server `last_visit` field on list payload — not invented.
- Onboarding still missing (UX-01–04).
- Prescriptions list not a separate patient-chart tab; prescriptions remain via encounters/timeline when present.

## Unverified

Authenticated browser screenshots and interaction E2E (see visual verification doc).
