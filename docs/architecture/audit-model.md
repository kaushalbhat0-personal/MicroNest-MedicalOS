# Audit Model (P1)

`audit_events(id, occurred_at, tenant_id, actor_type/id, action, resource_type/id,
encounter_id?, request_id?, reason?, before_ref?, after_hash?, result,
chain_day, prev_hash, event_hash)`.

- Append-only: app role has INSERT+SELECT only (migration 0005).
- Hash chain per (tenant, day): `sha256(ts|tenant|actor|action|resource|prev)`.
  `verify_chain` recomputes; tamper test included.
- Refs only — never PHI/payloads (enforced by review + log-scrub tests).
- Reading audit appends `audit.read` (single entry, resource = tenant audit).
- Security `auth_events` (login/refresh/reset/reuse) are separate, internal-only.
