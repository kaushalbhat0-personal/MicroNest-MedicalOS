# Practitioner Management

## Distinction

| Concept | Purpose |
|---------|---------|
| Staff / membership | Tenant employment + RBAC |
| Practitioner | Clinical identity for bookings and clinical writes |

These are **not** merged in UI or API.

## Screen

`StaffHub` → **Practitioners** tab

## API

| Action | Endpoint | Permission |
|--------|----------|------------|
| List | `GET /tenants/{id}/practitioners` | `appointment.read` |
| Register | `POST /tenants/{id}/practitioners` | (existing backend rule) |
| Verification queue | `GET /tenants/{id}/verification` | `staff.manage` |
| Set verification | `POST /tenants/{id}/verification` | `staff.manage` |

## Displayed

- Practitioner id, display_name  
- verification_status (`pending` / `approved` / `rejected`)  
- Linked `user_id` when provided at registration  

## Rules preserved

- Unapproved practitioners must not receive bookings (scheduling backend)  
- Ordinary staff cannot approve themselves without `staff.manage`  
- Clinician-linked practitioner still required for clinical writes (M7)  

## State transitions

`pending` → `approved` | `rejected` (via verification POST)

## Tests

- Backend: tenants / scheduling verification coverage  
- Desktop: Practitioners tab; evidence `practitioners_list` / `verification_queue`
