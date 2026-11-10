# Deployment architecture (P7)

Modular monolith, same containers in every model. Profiles
(`ENV` × `DEPLOYMENT`) validate operational configuration; domain behavior
never branches on deployment.

## Topology

CLOUD (preview = this slice, minus managed services):
web → API → Postgres (app role, RLS) ; worker → outbox → notify provider ;
API → S3-compatible private storage. Reverse proxy + TLS terminates in front
(preview-local is plain HTTP with localhost-only origins).

PRIVATE CLOUD: dedicated app + DB + storage + secrets per customer,
platform-team upgrades, customer-owned backups (runbook in
`docs/database/p7-operations.md`).

ON-PREM: local API + Postgres + MinIO + worker; no inbound DB exposure, no
port forwarding; notifications unavailable unless the customer provides a
provider (documented gap); future portal access via the outbound-only relay
(contract in `docs/decisions/P7-03-storage-notify-relay.md`).

## Readiness matrix (evidence / gap)

| Capability | Cloud (preview) | Private | On-prem | Evidence / gap |
|---|---|---|---|---|
| PostgreSQL + RLS | ready | ready (dedicated) | ready (local) | migrations 0001–0014, `FORCE RLS`, restore checks |
| Private storage | ready (MinIO/S3) | ready (config) | ready (MinIO) | `S3StorageAdapter` + smoke test; bucket pre-created in prod |
| Worker | ready | ready | ready | boot validation, `--once`, dead-letter signal |
| Notifications | unavailable (honest) | unavailable | unavailable | `NOTIFY_PROVIDER=none`; SES/SMS post-P7 |
| AuthN/Z, cookies, TLS | ready (local exception) | ready | ready (local) | boot validation; TLS by terminator |
| Backups | scripted, exercised | runbook | runbook | `backup/restore-preview.sh`; RPO/RTO proposed |
| Updates/rollback | migrate job + forward-fix | controlled | customer-run | `db-migrate.sh`, ADR P7-02 |
| Monitoring | logs + health endpoints | same | same | request IDs, scrubbed logs, no PHI |
| Licensing (offline grace) | n/a (SaaS) | n/a | NOT implemented | stub; P2 carryover |
| Portal access | preview-local | dedicated domain | relay (future) | localhost stack; outbound-only contract, no sync code |
| White-label branding | NOT implemented | NOT implemented | NOT implemented | stub; constraint recorded |

## Operational limitations (explicit)

- Single-replica rate limiting (in-memory; Redis seam documented).
- One web image per domain (`NEXT_PUBLIC_API_URL` baked at build).
- RPO ≤ 24h / RTO ≤ 4h are proposed targets, not measured guarantees.
- No production deployment, DNS, TLS certs, secret manager, or provider
  accounts are provisioned in P7 — external prerequisites are listed in
  `docs/database/p7-operations.md`.
