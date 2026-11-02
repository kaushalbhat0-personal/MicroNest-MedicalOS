# Tenant Isolation (P1, locked)

Isolation begins at `get_ctx`: scope is derived from session → user →
memberships, never from client input. `X-Tenant` is a selector among MY
memberships; mismatches are 403/404 without confirming existence.

Layers: (1) service tenant checks, (2) router tenant-match (404, never oracle),
(3) RLS fail-closed at the database, (4) per-PR isolation + RLS test suites.

Cross-tenant reads/writes/updates/deletes are proven impossible at layers
2–4; platform admins have NO clinical path (metadata endpoints only, no
tenant context, no bypass).
