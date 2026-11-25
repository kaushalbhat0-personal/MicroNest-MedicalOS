# Security and Tenant Isolation — M9

## Controls

| Control | Implementation |
|---------|----------------|
| Authenticated client | Desktop `apiFetch` with native Bearer |
| Tenant context | `X-Tenant` from session workspace; not free-form user invent |
| RBAC | Backend permissions on every staff/invite/schedule/leave/verification route |
| Invitation tokens | Shown once in UI; cleared on dismiss; never logged; evidence redacts |
| Privilege escalation | Role PATCH behind `staff.manage` + last-admin backend guard; ConfirmDialog |
| Practitioner approval | `staff.manage` only; distinct from staff profile |
| Logout / workspace switch | Session clear drops workforce React state with remount |
| Logging | No email+token pairs in console |

## Cross-tenant

Evidence probe: request staff for a random foreign tenant id → denied (401/403/404).  
Backend isolation suite remains authoritative (`tests/isolation/`, `test_staff.py`).

## Unauthorized role change

Without `staff.manage`, Directory edit UI is hidden. Direct API PATCH returns 403.

## Invitation secrets

Frontend never generates tokens. Accept flow uses existing invite APIs. Desktop does not store invite tokens in DPAPI or localStorage.
