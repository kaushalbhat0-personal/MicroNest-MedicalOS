# Request Authentication & Tenant-Scope Flow (P1)

```
Cookie/Bearer access JWT (10 min)
  → get_current_user: verify signature+typ+expiry → load session row
    (revoked? expired? user active?) → SET app.user_id (RLS actor)
  → get_ctx: memberships of user (RLS: user match)
    → X-Tenant validated against memberships (selector only)
    → tenant active? → SET app.tenant_id (RLS tenant)
    → role permissions → location scope (tenant-scoped read)
    → RequestContext (frozen dataclass)
  → require("<permission>"): platform perms need is_platform_admin flag,
    tenant perms need catalog membership. Deny by default.
```

Notes:

- AuthN failures return 401 WITHOUT raising, so the txn commits and the
  security-audit write (failed login / reuse detection / revocation) persists.
  Raising there would roll the evidence back (fixed during P1, see decisions).
- Refresh rotation: present secret must match current row; a rotated (old)
  secret re-presented revokes the whole family (theft response).
- `X-Tenant` with multiple memberships and no header → 403 "selection required".
- Platform endpoints (`/platform/*`) use `get_platform_admin` (user flag, no
  tenant) and manage RLS explicitly for service-verified IDs only.
