# Cross-Platform Synchronization Design

**Phase:** A0 — architecture / feasibility (no sync engine implementation)  
**Date:** 2026-11-25

## 1. Problem

Web today is **online-only**: `apps/web/lib/api.ts` calls FastAPI with `credentials: "include"`. There is **no** client local DB, outbox, or sync protocol in the repository.

The server has a **transactional outbox** (`outbox_events`) for reliable server-side side effects (notifications, workers). That must **not** be confused with a **device local outbox**.

Android and Windows require local-first capabilities while preserving:

- One authorization model  
- One tenant boundary  
- One clinical source of truth (server)  
- Comparable audit semantics  

## 2. Design principles

1. **Server remains authoritative** for clinical state after sync.  
2. **Platform-specific key storage**; shared sync logic is crypto-agnostic.  
3. **Fail closed** when authz lease expires or device is revoked.  
4. **No silent PHI merges** — typed conflict policies only.  
5. **Least data locally** — sync scopes are explicit allowlists, not “mirror the DB”.  
6. **Idempotent pushes** — client-generated idempotency keys (already used in some server flows).

## 3. Shared contracts (language-agnostic)

### 3.1 SecureKeyStore (platform)

```
generateOrLoadMasterKey(deviceId) -> KeyHandle
wrap(dek) / unwrap(dek)
lock() / unlock(biometric|pin)
destroyAll()  // revoke / logout everywhere
```

| Platform | Implementation |
| --- | --- |
| Android | Android Keystore + BiometricPrompt |
| Windows | DPAPI / Credential Manager (+ optional Windows Hello) |
| Web (future optional) | Not in A0; if needed: WebCrypto + non-extractable keys (weaker offline story) |

### 3.2 EncryptedDatabase

```
open(path, dek)
migrate(version)
execute(sql|query)
close()
wipe()
```

Default engine target: **SQLCipher** (or audited equivalent) on Android and Windows.

### 3.3 AuthzLease

```
{
  device_id, user_id, tenants: [{id, permissions[]}],
  issued_at, expires_at,
  max_offline_ops?,
  server_sig?   // optional HMAC/JWT from API
}
```

Offline check: `now < expires_at && device_id matches && permission required`.

### 3.4 Local outbox

```
outbox_entries(
  id, tenant_id, entity_type, entity_id,
  op, payload_ref, idempotency_key,
  created_at, attempts, next_attempt_at, status
)
```

Payloads stored encrypted at rest; **never** log payload bodies.

### 3.5 SyncEngine

```
pull(scope, cursor) -> changes
push(outbox_batch) -> acks | conflicts
reconcile(conflicts) -> user_or_policy_resolution
```

Transport: HTTPS to existing `/api/v1` where possible; add **sync-specific endpoints** only when batching/cursors require them.

## 4. Synchronization protocol (proposed)

### 4.1 Scopes (MVP candidates)

| Scope | Offline write? | Notes |
| --- | --- | --- |
| `patients.demographics` | Limited | High value for reception |
| `appointments.day` | Limited | Conflict-prone; last-write with review |
| `encounters.draft_notes` | Yes | Must not skip consent gates on finalize |
| `billing.*` | **No** | Online-only initially |
| `communications.whatsapp` | **No** | Online-only |
| `portal.*` | **No** | Online-only |
| `documents.bytes` | Lazy | Metadata sync; bytes on demand |

### 4.2 Pull

1. Client presents Bearer + device_id + cursor per scope.  
2. Server returns ordered mutations `{entity, id, version, deleted, body}` filtered by tenant + permissions.  
3. Client applies in transaction; advances cursor only after durable commit.

### 4.3 Push

1. Drain outbox FIFO per tenant.  
2. Map to existing REST commands when 1:1 (preferred).  
3. On 409/422 → conflict record; block entity until resolved.  
4. On 401/403 device revoke → wipe local DB + clear SecureKeyStore.

### 4.4 Conflict policy (default)

| Entity class | Policy |
| --- | --- |
| Server-authoritative clinical finalize | **Server wins**; local draft preserved as conflict copy |
| Concurrent demographic edits | Field-merge if disjoint; else manual |
| Deletes vs updates | Delete wins if server deleted; else resurface |

## 5. Authorization leases & offline rules

| Rule | Behavior |
| --- | --- |
| Lease missing/expired | Block writes; allow encrypted read of already-synced data **or** full lock (product choice — default **block writes**) |
| Permission not in lease | Deny even if UI shows control |
| Tenant switch | Separate local partitions; never join across tenants |
| Role downgrade on sync | Recompute UI; purge illegal cached rows |

## 6. Audit event delivery

- Local actions that would have produced server audit should enqueue `audit_local` outbox items.  
- On push success, server emits canonical audit (existing patterns).  
- Do not treat local-only logs as compliance-complete until server ack.

Align with existing principle: clinical content stays out of coarse audit payloads where current modules already forbid it.

## 7. Cache expiration

| Data | TTL / trigger |
| --- | --- |
| AuthzLease | Short (hours), refresh on foreground |
| List caches | Scope cursor + max age |
| Document bytes | LRU disk quota; re-fetch via signed URL flow |
| On logout / revoke | Immediate wipe |

## 8. Relationship to server outbox

| Server `outbox_events` | Device local outbox |
| --- | --- |
| Written in same DB transaction as domain row | Written on device before/without server commit |
| Worker dispatches notifications/etc. | SyncEngine pushes to API |
| Not exposed to clients for writes | Never uploaded as raw table dump |

## 9. API gaps to schedule (not built in A0)

1. Bearer token issuance suitable for native (without weakening web cookies).  
2. Device registration + revocation endpoints.  
3. Authz lease minting endpoint.  
4. Optional bulk sync cursors if REST chatty-ness is insufficient.  
5. `min_client_version` gate.

## 10. Implementation package plan (post-approval)

```
packages/sync-core/          # pure TS: outbox, cursors, conflict types
packages/local-db-contract/  # interfaces only
packages/api-client/         # fetch wrapper: cookie adapter | bearer adapter
platform/android-secure/     # Keystore + SQLCipher
platform/windows-secure/     # DPAPI + SQLCipher
```

## 11. Sync readiness verdict

| Question | Verdict |
| --- | --- |
| Design completeness for A0 | **Sufficient to proceed to ADR + spike** |
| Shared sync implementation ready to code end-to-end | **No** — blocked on API token/device/lease contracts + MVP scope freeze |
| Can Android/Windows ship without sync? | Online-only WebView/SPA shells **possible** but fail the local-first product requirement |
| Risk if rushed | Divergent offline rules, PHI leakage in logs, silent conflicts |

**Readiness for shared synchronization implementation:** **CONDITIONAL** — architecture approved for spikes; full implementation **not** cleared until gaps in §9 are ADRed.
