# A3 — Shared client contract audit + proposal

**Implementation verdict: FAIL** (device/lease/outbox APIs do not exist on FastAPI).  
**Audit + proposal verdict: PASS** (gaps mapped to concrete contracts; evidence-backed against current code).

Full proposal text: `experiments/native-client-poc/shared/contracts/device-client-contracts.md`

## Audit method

Inspected (no production deploy changes):

- `backend/app/api/deps.py` — cookie **or** Bearer access token; session row must be active
- `backend/app/api/v1/auth.py` — login/refresh/logout/me; cookies via `issue_session_pair`
- `backend/app/api/v1/_shared.py` — creates JWT access + refresh cookie; **no JSON token fields**
- `backend/app/modules/identity/models.py` — `Session.refresh_hash`; no `device_id`
- `backend/app/platform/events/outbox.py` — server `outbox_events` (domain bus)
- Grep: no device registration / authorization lease / device sync routes

PoC mock API (`experiments/native-client-poc/shared/mock-api/server.mjs`) demonstrates **desired native Bearer shape only** — not production behavior.

## Gap matrix (A0 → evidence)

| Capability | Required for native | Backend today | Status |
|------------|---------------------|---------------|--------|
| Cookie web auth | Keep unchanged | Implemented (`hos_access` / `hos_refresh`) | **PASS** (existing) |
| Bearer acceptance | Native calls | `_read_access_token` prefers Bearer | **PASS** (existing) |
| Login returns usable native tokens | Native bootstrap | Login returns `MeResponse` only; tokens in **Set-Cookie** | **FAIL** for native UX |
| Refresh without cookie jar | Native | Refresh reads **refresh cookie only** | **FAIL** for native |
| Device registration | Revocation / binding | Missing | **NOT IMPLEMENTED** |
| Device identity / public key PoP | Binding | Missing | **NOT IMPLEMENTED** |
| Device-bound token lifecycle | Revoke per device | Sessions exist; not device-scoped | **NOT IMPLEMENTED** |
| Authorization lease | Offline authz window | Missing | **NOT IMPLEMENTED** |
| Device revoke | Kill offline window early on next contact | Missing | **NOT IMPLEMENTED** |
| Device sync pull/push | Assigned patients / appointments | Missing | **NOT IMPLEMENTED** |
| Device outbox + ack | Durable ops | Missing | **NOT IMPLEMENTED** |
| Idempotency on device ops | Safe retry | Partial patterns elsewhere; not device outbox | **NOT IMPLEMENTED** |
| Conflict handling policy | Clinical safety | Not encoded for device sync | **NOT IMPLEMENTED** |
| Server audit for device ops | Evidence | Audit exists for auth; not device sync | **NOT IMPLEMENTED** |
| Server `outbox_events` | Async domain | Exists | **PASS** — **≠** device outbox |

## Critical auth finding (blocker)

Native clients **cannot** complete production login today by reading JSON alone:

1. `POST /api/v1/auth/login` sets HttpOnly cookies; response body has user/tenants only.
2. `POST /api/v1/auth/refresh` requires the refresh **cookie**.
3. Bearer works **if** the client already possesses the access JWT.

**Recommended change (same auth system, not a second one):**

- Add `client_platform` / `device_id` to login (after device register), and when platform ∈ {android, windows}:
  - Still create the same `Session` row + JWT (`sub`, `sid`).
  - Additionally return `access_token` + `refresh_token` (or `session_id.secret`) in JSON for secure OS storage.
  - Optionally skip cookie set for native User-Agents.
- Bind `sessions.device_id` (nullable for web).
- Keep web cookie path untouched.

Do **not** invent a parallel OAuth server unless product later requires third-party IdP.

## Contract proposal (summary)

### Device identity

- `POST /devices/register` → `device_id`, tenant/user from auth, platform, app_version, public_key_jwk
- `POST /devices/{id}/revoke` → invalidate device refresh + leases

### Authentication

- Web cookies unchanged
- Native Bearer + OS secure store
- Short access TTL (existing `ACCESS_TOKEN_MINUTES`); rotatable refresh; logout revokes session

### Authorization lease

- Issued scopes for assigned-patient read / upcoming appointments
- `expires_at` + clinic-configurable `max_offline_hours` (not a universal constant)
- Offline past expiry: block clinical cache; show reconnect UX
- Role/membership revoke: enforced on next online refresh; offline until lease end only

### Device outbox

Fields: `operation_id`, `device_id`, `tenant_id`, `actor_id`, `entity_type`, `entity_id`, `operation_type`, `base_version`, `payload`, `device_created_at`, `server_received_at`, `status`, acknowledgment / `audit_event_id`.

**Server derives** tenant_id and actor_id; client values are not trusted.

### Conflict policy

- No silent LWW on clinical signed records — amend + audit
- Financial: explicit reconciliation
- Demographics: documented field authority
- Every accept/reject audited

### Offline access scope (A0 preserved)

- Assigned patients only
- Upcoming appointments (default **7 days**, configurable)
- Minimum demographics + explicitly authorized clinical subsets
- No full-clinic download
- **Offline clinical writes OFF** until a later phase

## What compiling models would not prove

TypeScript/Pydantic shapes alone are **insufficient** for PASS. This audit treats contracts as **FAIL** until FastAPI routes, persistence, and tests exist.

## PoC mock vs production

| Behavior | Mock PoC | Production FastAPI |
|----------|----------|--------------------|
| Login JSON includes `access_token` | Yes | **No** |
| Bearer `/me` | Yes | Yes (if token held) |
| Device APIs | No | No |

## Shared architecture verdict

**FAIL for readiness** — device identity, native token issuance, lease, and device outbox must be built before either client can ship offline clinic features. Proposal is ready for an implementation phase **after** Windows crypto path and before Android lab completion.
