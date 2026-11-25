# Staff Schedules

## Distinction

| Concept | API | Meaning |
|---------|-----|---------|
| Staff work schedule | `/staff-schedules` | HR working windows on a **membership** |
| Appointment availability | `/availability` | Bookable slots for a **verified practitioner** |

Desktop Schedules tab captions this distinction.

## Screen

`StaffHub` → **Schedules** tab

## API

| Action | Endpoint | Permission |
|--------|----------|------------|
| List | `GET /tenants/{id}/staff-schedules?membership_id&location_id` | `staff.manage` |
| Create | `POST /tenants/{id}/staff-schedules` | `staff.manage` |
| Deactivate | `POST /tenants/{id}/staff-schedules/{id}/deactivate` | `staff.manage` |
| PATCH / edit in place | **MISSING** | — |

## Fields

- membership_id, location_id  
- weekday (0=Mon … 6=Sun — `WEEKDAY_LABELS`)  
- start_time, end_time, break_minutes  
- effective_from, effective_to, is_active  

## Validation

Client checks time range ordering before submit; backend enforces remaining constraints. No invented recurring rules or conflict engine beyond backend.

## Tests

- Backend: `test_staff.py` schedule cases  
- Desktop: Schedules tab; evidence create/deactivate
