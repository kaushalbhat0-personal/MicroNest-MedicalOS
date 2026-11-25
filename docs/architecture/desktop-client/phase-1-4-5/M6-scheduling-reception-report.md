# M6 — Scheduling and Reception Report

**Verdict: PASS**

## Implemented

| Feature | Desktop surface | Notes |
|---------|-----------------|-------|
| M6.1 Calendar | `ScheduleCalendar` | Day + week views; location/practitioner filters; status styling |
| M6.2 Booking | Book panel | Patient search, practitioner, location, **server availability slots**, duration, notes |
| M6.3 Reschedule/cancel | Detail panel | PATCH reschedule (scheduled/confirmed only); cancel ConfirmDialog |
| M6.4 Walk-in | `ReceptionQueue` | Existing patient or quick register + `walk_in=true` |
| M6.5 Check-in | Queue actions | `POST .../status` → `checked_in`; shows queue token; duplicate check-in handled by backend idempotency/errors |
| M6.6 Queue | Reception | Bucketed API flattened; **15s polling** (not push); location/day/practitioner filters |
| M6.7 Status | Calendar + reception | Frontend `STATUS_TRANSITIONS` mirrors backend; no `in_progress` |

## Status matrix (backend-authoritative)

| From | To |
|------|-----|
| scheduled | confirmed, checked_in, cancelled, no_show |
| confirmed | checked_in, cancelled, no_show |
| checked_in | completed, cancelled |
| completed / cancelled / no_show | (terminal) |

## Missing / not invented

- No WebSocket push for queue (documented as polling)
- No separate reschedule-history API (cancel/reschedule audit fields on appointment only)
- Availability empty → booking can fail with conflict if free-form start used; UI prefers slots

## Blockers

None for M6 acceptance against existing APIs.
