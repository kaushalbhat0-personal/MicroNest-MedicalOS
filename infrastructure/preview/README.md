# Preview deployment (P7 cloud preview vertical slice)

Isolated, reproducible, local-cost. The preview stack mirrors the cloud
topology (API + worker + Postgres + S3-compatible storage + web) with
placeholder secrets and no production data, DNS, or money.

## Prerequisites

- Docker with compose v2.
- `infrastructure/preview/preview.env.example` copied to `.env.preview` (gitignored).
- No production credentials on this machine path (the boot validator refuses
  preview database names and blocks prod-shaped config).

## Bring-up

```bash
cp infrastructure/preview/preview.env.example .env.preview
# edit .env.preview — every change-me value must be replaced
set -a; source .env.preview; set +a   # or export manually (PowerShell: see below)

docker build -f backend/Dockerfile -t healthcare-os-backend:preview .
docker build -f apps/web/Dockerfile \
  --build-arg NEXT_PUBLIC_API_URL=http://localhost:8001 \
  -t healthcare-os-web:preview .

docker compose -f infrastructure/preview/docker-compose.yml --env-file .env.preview up -d db storage
docker compose -f infrastructure/preview/docker-compose.yml --env-file .env.preview run --rm migrate
docker compose -f infrastructure/preview/docker-compose.yml --env-file .env.preview up -d api worker web
```

PowerShell equivalent for loading the env file:

```powershell
Get-Content .env.preview | Where-Object { $_ -match '=' -and $_ -notmatch '^#' } | ForEach-Object {
  $k, $v = $_.Split('=', 2); Set-Item "env:$k" $v
}
```

## Verify

```bash
curl http://localhost:8001/api/healthz   # {"status":"ok"}
curl http://localhost:8001/api/readyz    # {"status":"ready"}
```

Then run `scripts/preview-smoke.sh` (fails the gate on any secret/PHI-shaped
log line, non-private storage, or broken logout/revocation).

Operator caution: `docker compose config` interpolates and PRINTS secrets.
Never paste its output into tickets or logs.

## What preview does NOT prove

- TLS termination (local stack is plain HTTP; `COOKIE_SECURE=false` is
  accepted only for localhost-only origins — production requires `true`).
- Real notifications (`NOTIFY_PROVIDER=none`; delivery is explicitly
  unavailable and `send()` fails closed).
- Managed Postgres PITR, S3 durability, SES/SMS, secret-manager wiring,
  multi-replica rate limiting. See `docs/architecture/deployment.md`.

## Tear down

```bash
docker compose -f infrastructure/preview/docker-compose.yml --env-file .env.preview down -v
```

Volumes are preview-scoped (`preview-pgdata`, `preview-miniodata`). The
production database is never referenced by any preview manifest.
