# Invitations and RBAC

## Invitations

| Action | Endpoint | Permission |
|--------|----------|------------|
| Create | `POST /tenants/{id}/invites` | `staff.invite` |
| List | `GET /tenants/{id}/invitations?status=` | `staff.invite` |
| Revoke | `POST /tenants/{id}/invitations/{id}/revoke` | `staff.invite` |
| Accept | `POST /invites/accept` (+ authenticated variants) | public / session |

### Desktop behavior

- Form: email, role (from `GET /roles`), optional TTL  
- Token returned **once** in an Alert with copy button; dismissed state clears token from React state  
- Token is never logged; evidence scripts never persist tokens  
- Caption: invitation **created ≠ email delivered** (delivery may be absent)  
- No automated WhatsApp; operator may copy token manually  
- Acceptance remains the existing web/portal flow (not reinvented in desktop)

### State transitions

`pending` → `accepted` | `revoked` | expired

## Roles and permissions

| Action | Endpoint | Permission |
|--------|----------|------------|
| List roles | `GET /tenants/{id}/roles` | `tenant.read` |
| Create custom role | `POST /tenants/{id}/roles` | `roles.manage` |

Desktop lists roles for invite/role selects. Role assignment on staff uses `PATCH /staff/{id}` with `role`.

### Declared but unused HTTP permissions

`schedule.manage`, `queue.manage`, `reports.view`, `reports.export`, `support.grant` — present in permission catalog / seeds but not wired to these workforce adapters.

### Safety

- No new role system  
- No automatic admin grants  
- Frontend navigation is not authorization; backend enforces every mutation  
- Sensitive role change: ConfirmDialog before PATCH

## Tests

- Backend: `test_invite_list_revoke_and_authenticated_accept`  
- Desktop: Invitations tab + evidence `invitation_create` / `invitation_revoke`
