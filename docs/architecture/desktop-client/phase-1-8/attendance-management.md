# Attendance Management

## Screen

`StaffHub` → **Attendance** tab

## API

| Action | Endpoint | Permission |
|--------|----------|------------|
| Check-in | `POST /tenants/{id}/attendance/check-in` | `tenant.read` |
| Check-out | `POST /tenants/{id}/attendance/check-out` | `tenant.read` |
| List | `GET /tenants/{id}/attendance?membership_id&location_id&from_date&to_date` | `tenant.read` / manage filters |
| Correct | `POST /tenants/{id}/attendance/{id}/correct` | `staff.manage` |

## Supported UX

- Self check-in / check-out  
- History with date filters  
- Manager correction with **required reason** (auditable)  

## Explicitly out of scope

- Biometric attendance  
- GPS tracking  
- Automatic silent time tracking  
- Silent historical edits without reason  

## State

Open record (check-in) → closed (check-out); corrections append reason, do not invent parallel history stores.

## Tests

- Backend: `test_staff.py` attendance  
- Desktop: Attendance tab; evidence check-in/out/list
