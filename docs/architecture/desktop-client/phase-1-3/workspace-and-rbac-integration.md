# Workspace and RBAC integration

## Workspace selection

1. Native login / refresh returns `tenants[]` (server-derived memberships).  
2. Single tenant → auto-select + `workspace-context`.  
3. Multiple tenants → explicit picker; no clinic entered until selection.  
4. Switch clinic clears tenant-scoped UI state (`workspace` context) and re-fetches.

`X-Tenant` set on all tenant API calls. Roles/permissions never trusted from client input.

## RBAC

| Source | Use |
|--------|-----|
| `workspace-context.permissions` | Nav filter + dashboard variant hints |
| FastAPI `require()` | Authoritative on every protected route |

### Declared but unused permissions (unchanged)

`settings.manage`, `schedule.manage`, `queue.manage`, `documents.*`, `branding.manage`, `reports.*` — catalog/seed only; desktop does not invent endpoints for them.

### Seed roles supported in UX

doctor, receptionist, tenant_admin (plus nurse/accountant heuristics). Patient portal role must not receive clinic shell (no clinic memberships → empty tenants).
