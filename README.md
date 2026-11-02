# Healthcare OS

Multi-specialty healthcare operating platform. Dental is the first vertical.

**Phase: P1 Platform Skeleton** — secure foundation only (identity, tenancy,
authorization, audit, ports). No scheduling, clinical, dental, billing, portal,
subscription, or licensing domains yet.

## Layout

- `apps/web` — staff/admin web app (Next.js, minimal in P1)
- `apps/patient-portal` — scope note (P5)
- `apps/platform-admin` — scope note (P5)
- `backend/` — FastAPI modular monolith
- `packages/ui|contracts|config` — shared design system, API contracts, configs
- `infrastructure/cloud|private|on-premise` — deployment adapters + dev compose
- `docs/` — product, architecture, security, database, decisions
- `tests/` — unit, service, api, isolation, contract, deployment

## Quick start (dev)

```powershell
cp .env.example .env            # then edit secrets
docker compose -f infrastructure/dev/docker-compose.yml up -d
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
$env:DATABASE_URL = "postgresql+psycopg2://hos_owner:..."  # see .env.example
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

Bootstrap a platform admin + first tenant (prints invite token):

```powershell
.\.venv\Scripts\python.exe -m app.platform.ops --app-dir backend bootstrap --email admin@example.com
```

Run tests (needs dev Postgres up):

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Constitution: `docs/architecture/`, ADRs in `docs/decisions/`.
Phase 0/0.5 specs are the authority; do not silently deviate.
