# Staff Directory and Profiles

## Screen

`StaffHub` → **Directory** tab (`/staff`)

## API

| Action | Endpoint | Permission |
|--------|----------|------------|
| List | `GET /tenants/{id}/staff?q&active_only&location_id` | `staff.manage` |
| Get | `GET /tenants/{id}/staff/{membership_id}` | `staff.manage` |
| Update | `PATCH /tenants/{id}/staff/{membership_id}` | `staff.manage` |

## Displayed fields

- Identity: membership_id, user_id, email, display_name  
- Role + permissions (read-only from membership)  
- Active / inactive (`is_active`)  
- Location associations (`location_ids`)  
- Designation, phone, employment_status, joined_at, notes  
- Practitioner association is shown on the Practitioners tab (orthogonal record)

## Editable vs read-only

| Editable (PATCH) | Read-only |
|------------------|-----------|
| designation, phone, employment_status, joined_at, notes | email, user_id, membership_id |
| location_ids, role, is_active | permissions array (derived) |

Role changes require ConfirmDialog explaining the target role. Backend enforces last-admin guards.

## Search / filters / bounds

- Client search `q` forwarded to API  
- Active-only / inactive / all filter  
- Location filter  
- Does not download unbounded workforce beyond API response; filters reduce scope

## Tests

- Backend: `tests/api/test_staff.py::test_staff_directory_and_profile`  
- Desktop: StaffHub Directory tab; `staffApi` typecheck; evidence `staff_directory` / `staff_profile`

## State transitions

`employment_status`: active ↔ on_leave ↔ terminated (via PATCH).  
`is_active` membership flag toggled via PATCH when authorized.
