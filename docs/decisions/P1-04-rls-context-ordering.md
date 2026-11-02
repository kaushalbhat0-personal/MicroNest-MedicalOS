# P1-04 — Actor context set at authentication; tenant set after selection

Date: 2026-11-02 · Status: accepted.

Context: RLS on `memberships` allows reads by user match, writes by tenant.
Reads issued before any `SET` failed closed, so login, tenant listing, and
location scoping all broke in sequence.

Decision: `get_current_user` sets `app.user_id` immediately (fail-closed for
everything else); `get_ctx` sets `app.tenant_id` right after the tenant
selector is validated and BEFORE any tenant-scoped read (roles, locations).

Consequences: ordering constraint is load-bearing — tenant-scoped reads must
never precede the tenant `SET` in `get_ctx`. Covered by location-scope tests.
