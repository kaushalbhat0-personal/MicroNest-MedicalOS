# P3.1-B — Workflow UX audit (pre-change baseline)

**Date:** 2026-11-24  
**HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**Prior work:** P3.1-A shell/nav complete; partial P3.1-B polish already present on these five screens.

## Scope

| Workflow | Route | Primary users |
|----------|-------|---------------|
| Dashboard | `/` | Owner, admin, receptionist, practitioner |
| Patient directory | `/patients` | Receptionist, admin |
| Patient 360° | `/patients/[id]` | Dentist, practitioner, receptionist |
| Appointments | `/schedule` | Receptionist, practitioner |
| Reception | `/reception` | Receptionist |

## Findings before P3.1-B refinement

### Dashboard
- Attention metrics existed but sat below workspace picker.
- No today’s appointment list despite `todays_appointments` on ops API.
- Outstanding amount not shown with `MoneyDisplay`.
- Error path was Alert-only (no retry).

### Patient directory
- Search + register worked; CSV always expanded.
- No active/inactive filter (client-side possible on loaded rows).
- No explicit “open chart” action column; long names unconstrained.
- Register did not navigate to the new chart.

### Patient 360°
- Seven flat tabs duplicated chronology (appointments/encounters/dental separate from timeline).
- Overview was prose-heavy, not scannable cards.
- WhatsApp used raw `<select>` / checkbox (UX-11).
- Deactivate lacked confirmation.
- Book action did not preselect patient on schedule.

### Appointments
- Missing patient/practitioner columns in list.
- Empty state not actionable (UX-15).
- Cancel without confirm dialog.
- Walk-in used raw checkbox; booking had no pending state.
- `?patient=` query unsupported.

### Reception
- Sections present but no summary strip (waiting / checked-in / next token).
- Completed & no-shows always visible (noise).
- No refresh control; empty waiting lacked walk-in CTA.
- Errors Alert-only.

## Backend contracts reused (no API changes)

- `GET .../locations/{id}/operations-dashboard` including `todays_appointments`
- `GET/POST .../patients`, import
- `GET .../patients/{id}/overview`, timeline, consents, WhatsApp link
- `GET/POST .../appointments` (+ status/cancel)
- `GET .../locations/{id}/reception-queue`

## Security constraints preserved

- Permission-aware dashboard metrics and nav.
- Server-side queue tokens only.
- No optimistic status/token assignment.
- Clinic notes remain on encounter screens; timeline titles/summaries only.
- WhatsApp remains user-initiated + consent-gated.
