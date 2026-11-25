# Device / lease / outbox contract proposal (A3)

Status: **PROPOSAL ONLY** — not implemented on FastAPI. Maps A0 gaps to concrete shapes.

## Principles

1. Web cookie auth (`hos_access` / `hos_refresh`) stays unchanged for Next.js.
2. Native clients use **Bearer** access tokens issued by the same auth service (extend existing JWT path already accepting `Authorization: Bearer` in `deps`).
3. Tenant and actor identity are **server-derived** from the authenticated session; client payload fields are ignored if they disagree.
4. Device outbox ≠ server `outbox_events` (domain event bus).

## Device identity

```http
POST /api/v1/devices/register
Authorization: Bearer <access>
Content-Type: application/json

{
  "platform": "android" | "windows",
  "app_version": "0.1.0",
  "device_label": "Clinic Tablet 3",
  "public_key_jwk": { "...": "device-bound key" },
  "attestation": null
}
```

Response:

```json
{
  "device_id": "uuid",
  "tenant_id": "uuid",
  "user_id": "uuid",
  "status": "active",
  "registered_at": "ISO-8601"
}
```

Revoke:

```http
POST /api/v1/devices/{device_id}/revoke
```

Effects: refresh tokens for that device invalidated; leases cancelled; further sync rejected with `device_revoked`.

## Authentication (native)

| Concern | Proposal |
|---------|----------|
| Login | Same credential endpoint; native response includes `access_token` + short-lived `refresh_token` bound to `device_id` |
| Storage | OS secure store only (Keystore/EncryptedSharedPreferences; DPAPI/Credential Manager) — never SharedPreferences/localStorage plaintext |
| Access TTL | 15 minutes (align existing) |
| Refresh TTL | configurable, max 7–30 days; rotatable |
| Logout | server revoke refresh + local wipe of tokens, leases, encrypted DB key material |
| Revocation offline | device keeps working until lease expiry; after that read-only cache until online re-auth |

## Authorization lease

```http
POST /api/v1/devices/{device_id}/leases
```

```json
{
  "lease_id": "uuid",
  "device_id": "uuid",
  "tenant_id": "uuid",
  "user_id": "uuid",
  "scopes": ["patients:assigned:read", "appointments:upcoming:read"],
  "expires_at": "ISO-8601",
  "max_offline_hours": 72,
  "policy_id": "clinic-default-offline-v1"
}
```

- `max_offline_hours` is **clinic policy**, not a universal constant (A0 suggested starting window for appointments: 7 days of schedule; lease/auth offline window separate).
- Role/clinic membership change: next online refresh fails; offline continues only until `expires_at`.
- After expiry offline: **deny clinical reads that require lease**; may show non-PHI “session expired — connect to clinic network”.

## Device sync + outbox

```http
POST /api/v1/devices/{device_id}/sync/pull
POST /api/v1/devices/{device_id}/sync/push
```

Push body (client-proposed; server re-binds identity):

```json
{
  "operations": [
    {
      "operation_id": "uuid",
      "entity_type": "appointment_note_draft",
      "entity_id": "uuid",
      "operation_type": "create|update|delete|amend",
      "base_version": 3,
      "payload": {},
      "device_created_at": "ISO-8601"
    }
  ]
}
```

Server acknowledgment:

```json
{
  "results": [
    {
      "operation_id": "uuid",
      "status": "accepted|rejected|conflict",
      "server_version": 4,
      "server_received_at": "ISO-8601",
      "audit_event_id": "uuid",
      "reason_code": null
    }
  ]
}
```

Required columns / fields for durable device outbox (client + server mirror):

| Field | Source of truth |
|-------|-----------------|
| operation_id | client UUID, idempotency key |
| device_id | server from auth device binding |
| tenant_id | server |
| actor_id | server |
| entity_type / entity_id / operation_type / base_version / payload | client, validated |
| device_created_at | client |
| server_received_at / status / acknowledgment | server |

**Phase A1/A2 / next phase: offline clinical writes remain OFF** — push endpoints accept only non-clinical drafts if anything; production clinical write path stays online-first until later phase.

## Conflict policy

- Clinical signed records: **never LWW**; require `amend` with audit trail.
- Financial: explicit reconciliation UI + ops.
- Demographics: documented merge policy (field-level authority: clinic master vs device).
- Every accept/reject → audit evidence.

## Offline access scope (unchanged from A0)

- Assigned patients only.
- Upcoming appointments (default **7 days**, configurable).
- Minimum necessary demographics.
- Explicitly authorized clinical subsets only.
- No full-clinic download.

## Gap audit vs current backend

| Capability | Backend today | PoC status |
|------------|---------------|------------|
| Cookie web auth | Implemented | Unchanged |
| Bearer JWT accept | Implemented in deps | Proven via mock for native shape |
| Device register/revoke | **Missing** | Contract only |
| Device-bound refresh | **Missing** | Contract only |
| Authorization lease | **Missing** | Contract only |
| Device sync pull/push | **Missing** | Contract only |
| Device outbox ack | **Missing** | Contract only |
| Server `outbox_events` | Exists (domain) | **Not** device outbox |
