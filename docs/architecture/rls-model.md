# RLS Model (P1, defense-in-depth)

Application authorization is authoritative. RLS guarantees a missing tenant
filter fails closed instead of leaking.

- Session tenant/user set per transaction via `SET LOCAL` in `get_ctx`
  (`app.tenant_id`, `app.user_id`); actor set in `get_current_user`.
- Policies (`0005_rls`): tenant-owned tables
  `locations, memberships(+scope), membership_locations, roles, verifications, audit_events`
  with `USING/WITH CHECK tenant = setting` (memberships also allow user match
  for reads so login/switcher work pre-tenant).
- `audit_events`: no UPDATE/DELETE policy + privilege revoked from app role.
- NOT RLS'd (documented exceptions, service-guarded + tested):
  `users/credentials/sessions/password_resets/practitioners/auth_events`
  (global identity), `tenants` (registry), `outbox_events` (internal; no API
  exposes it — asserted by contract/isolation tests), `invitations`
  (capability-gated by 256-bit token hash; see decisions/P1-01).
- `FORCE ROW LEVEL SECURITY` so table owners don't silently bypass in tests;
  app connects as `hos_app` (least privilege, grants in 0005).
