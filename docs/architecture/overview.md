# Architecture Overview (P1)

Modular monolith: one FastAPI app, strict module ports. Cross-module access
only through declared services/ports — enforced by `tests/` + dependency lint
(P2: add import-linter rule; P1 rule is documented + reviewed).

```
apps/web                  staff/admin UI (Next.js, HttpOnly cookies)
backend/app/main.py       wiring ONLY (routers, middleware, error handlers)
backend/app/modules/      identity · tenancy · clinics · audit · notifications
                          + P2+ stubs (scheduling, patients, encounters, ...)
backend/app/platform/     config · db · security · authz · ports · adapters
                          events (outbox/worker) · logging · ratelimit · ops
backend/alembic/          0001–0006, fresh history (legacy chains frozen)
packages/ui               shared tokens + primitives (P5 builds full system)
infrastructure/dev        compose (registry) + local_pg.py (embedded binaries)
tests/                    unit · service · api · isolation · contract · deployment
```

Constitution rules with teeth in P1: no `users.tenant_id`; sessions in DB with
rotation + reuse detection; permission catalog (no raw role checks);
tenant scope server-derived; RLS fail-closed; audit append-only + hash-chained;
ports for storage/notify; no migrate-at-startup; no SQLite anywhere.
