# Database Conventions (P1, locked)

- PostgreSQL only. No SQLite, no dialect forks — enforced by review + CI
  (postgres service) + the absence of any compatibility shim.
- `uuid v7` PKs (`platform/ids.py`), `timestamptz` everywhere, app writes UTC,
  presentation tz per location (default Asia/Kolkata).
- `tenant_id UUID NOT NULL` on every tenant-owned row (no legacy nullables).
- FKs on all relations with explicit `ON DELETE` behavior; indexes on all FKs;
  composite `(tenant_id, …)` where hot; partial uniques where needed (P2+).
- `created_at/updated_at` (+`created_by` where meaningful).
- Money: NUMERIC (P4; no floats anywhere — lint rule then).
- JSONB only for `permissions[]`, `payload`, opaque provider data — never for
  queryable domain facts.
- Enums as CHECK-safe strings in P1 (status fields); Postgres enums for
  stable P2+ state machines.
