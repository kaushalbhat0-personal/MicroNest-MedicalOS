# RLS Operations (P1)

- Policies live in `0005_rls` (+ amendments as new migrations, never edits
  once released — the invitations exemption below predates any release).
- App connects as `hos_app` (least privilege); migrations/seeds as owner.
- `FORCE ROW LEVEL SECURITY` everywhere RLS is enabled.
- Exceptions (service-guarded, tested): identity registry, tenants registry,
  outbox (internal, no API surface), invitations (capability-gated tokens),
  auth_events (internal sink).
- Debugging: `SET app.tenant_id`/`app.user_id` manually in psql; policies use
  `NULLIF(current_setting(...), '')` so "unset" fails closed, never open.
