# Cross-Platform Client Architecture

**Phase:** A0 — architecture / feasibility (no APK/EXE builds)  
**Date:** 2026-11-25  
**Scope:** Web (existing), Android (signed APK/AAB), Windows desktop (signed EXE)

## 1. Product constraint

Healthcare OS must ship **three first-class clients** that share:

| Shared contract | Owner today |
| --- | --- |
| Backend HTTP APIs (`/api/v1/*`) | FastAPI (`backend/app/api/v1/router.py`) |
| Authentication / session model | Identity module + HttpOnly cookies **or** Bearer (`deps.get_current_user`) |
| Authorization (roles, permissions, RLS) | `require()`, `X-Tenant`, Postgres RLS |
| Tenant / membership model | Tenancy module |
| Clinical / billing / portal business rules | Server modules (source of truth) |
| Audit semantics | Server audit + transactional **server** outbox (`outbox_events`) |
| Data residency | Deployment/env policy (cloud Render/Supabase staging today) |

Clients may cache and queue **locally**, but must not invent divergent clinical rules.

## 2. Repository compatibility evidence

| Observation | Evidence | Implication |
| --- | --- | --- |
| Web is Next.js 16 App Router | `apps/web/package.json` (`next@^16.4.6`) | Native shells cannot “just wrap” SSR as-is |
| UI is mostly client-side pages | 50+ `"use client"` files under `apps/web/app` | High reuse potential for a SPA/webview shell **if** routing is decoupled from Next SSR |
| Shared UI package | `packages/ui` (React 19 peer) | Preferred shared presentation layer |
| API client is fetch + credentials | `apps/web/lib/api.ts` | Cookie auth assumes browser + same-site proxy (P3.7D); native needs **Bearer / secure store** path |
| Bearer already accepted | `backend/app/api/deps.py`, auth module docstring | Native clients can use Authorization without inventing a parallel auth system |
| No mobile/desktop apps in monorepo | Only `apps/web`, `packages/ui`, `backend` | Greenfield client packages required |
| No client offline/sync engine | Grep: no Capacitor/Tauri/Electron/SQLCipher/IndexedDB sync | Sync is **net-new** |
| Server outbox exists | `backend/app/platform/events/outbox.py` | Server async jobs ≠ device local outbox; do not overload |
| Tenant selector is header | `X-Tenant` | All clients must send the same selector after auth |
| Threat model assumes untrusted clients | `docs/security/P3-6-threat-model.md` | Local DB is high-value PHI cache — encrypt + lease + revoke |

## 3. Recommended monorepo shape (future)

```
apps/
  web/                 # Next.js — primary online clinic/portal
  android/             # Capacitor or native host (decision below)
  desktop/             # Tauri 2 host (recommended) or Electron
packages/
  ui/                  # existing
  api-client/          # typed HTTP client (cookie OR bearer adapters)
  sync-core/           # outbox, leases, conflict rules (TS)
  local-db-contract/   # repository interfaces (no platform crypto)
platform/
  android-secure/      # Keystore + SQLCipher bindings
  windows-secure/      # DPAPI / Credential Manager + SQLCipher
```

**Rule:** platform packages implement `SecureKeyStore` + `EncryptedDatabase`; domain/sync never import Keystore or DPAPI directly.

## 4. Authentication model across platforms

| Platform | Session transport | Storage | CSRF |
| --- | --- | --- | --- |
| Web (Vercel) | HttpOnly cookies via same-origin `/api` proxy | Browser cookie jar | `SameSite=Lax` (no token layer today) |
| Android | **Bearer** access + refresh (or cookie jar inside WebView only if same-site) | Android Keystore-wrapped secrets; never plaintext SharedPreferences | N/A for bearer; pin certs / TLS |
| Windows | **Bearer** access + refresh | DPAPI or Windows Credential Manager; never plaintext files | Same |

Do **not** force `SameSite=None` cookies for native. Prefer explicit Bearer using existing FastAPI path.

**Device identity (new):** register `device_id` + public key / attestation metadata with the backend; bind refresh tokens to device for revocation.

## 5. Shared modules (contracts)

See also `cross-platform-sync-design.md`. Minimum interfaces:

1. `AuthSessionStore` — platform-specific  
2. `EncryptedDb` — open/migrate/close  
3. `EntityRepository<T>` — local CRUD by tenant  
4. `Outbox` — durable local mutation queue  
5. `SyncEngine` — pull/push, backoff, conflict hooks  
6. `AuthzLease` — offline permission snapshot with expiry  
7. `AuditBuffer` — local audit → server delivery  
8. `Clock` / `IdempotencyKey` — shared

## 6. Online vs offline authority

| Concern | Online | Offline |
| --- | --- | --- |
| Clinical writes | Server validates + RLS | Allowed only for lease-permitted ops; queued in outbox |
| Permission checks | Live `/me` + role permissions | Cached `AuthzLease` until expiry; deny if expired |
| Conflict | Server wins for clinical source-of-truth unless typed merge rule exists | Surface conflict UI; never silent PHI merge |
| Revocation | Immediate via refresh revoke | Detect on next sync; wipe/lock local DB |

## 7. Data residency

- Cloud residency remains deployment policy (region of Postgres/object storage).  
- Local device copies are **ephemeral caches** of tenant-authorized data.  
- Packaging must declare local PHI storage in privacy notices.  
- Clinic-controlled on-prem later can point all three clients at the same API base URL.

## 8. Final readiness verdict (A0)

| Track | Verdict | Why |
| --- | --- | --- |
| **Android APK development** | **NOT READY (architecture CONDITIONAL)** | Do not wrap current Next SSR in Capacitor. Need SPA shell + `@healthcare-os/ui`, Bearer/device auth contract, Keystore/SQLCipher/WorkManager wiring, signing ops. |
| **Windows EXE development** | **NOT READY (architecture CONDITIONAL)** | Prefer Tauri 2 + same SPA. Need DPAPI/Credential Manager key path (≠ Android Keystore), SQLCipher, Authenticode, signed updater. |
| **Shared synchronization implementation** | **NOT READY (design CONDITIONAL)** | Contracts defined; no client sync code exists. Blocked on token/device/lease API gaps + MVP sync scope ADR. Server `outbox_events` is not a device outbox. |

**A0 complete:** architecture and feasibility only — **no APK/EXE/sync engine builds** in this phase.

### Recommended sequence (post-approval)

1. ADR: native Bearer + device registration (preserve web cookies).  
2. ADR: MVP offline scopes (what may be written offline).  
3. Spike: Vite SPA shell sharing `@healthcare-os/ui`.  
4. Spike: Android Keystore↔SQLCipher and Windows DPAPI↔SQLCipher behind one interface.  
5. Only then: Capacitor APK and Tauri EXE packaging pilots (unsigned OK for internal spike; signed builds per `platform-packaging-and-signing.md`).

### Related documents

| Doc | Path |
| --- | --- |
| Android | `docs/architecture/android-client-architecture.md` |
| Windows | `docs/architecture/windows-desktop-architecture.md` |
| Sync | `docs/architecture/cross-platform-sync-design.md` |
| Packaging | `docs/architecture/platform-packaging-and-signing.md` |
