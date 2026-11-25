# Android Client Architecture

**Phase:** A0 — architecture / feasibility (no APK/AAB builds)  
**Date:** 2026-11-25

## 1. Goals

- Signed **APK/AAB** clinic (and optionally portal) client.
- Same FastAPI backend, tenant model, authz, audit semantics as web.
- Offline-capable local store with encryption and biometric unlock.
- Background sync without inventing a second clinical rules engine.

## 2. Technology options vs repository evidence

### Option A — Capacitor wrapping existing Next.js

| Criterion | Assessment |
| --- | --- |
| Fit to repo | **Poor–moderate.** App is Next.js 16 App Router with dynamic routes (`patients/[id]`, etc.) and server-oriented deployment (Vercel rewrite). Capacitor expects a static web asset root or a remote URL. |
| Remote URL WebView | Possible (load staging/production web) but **breaks offline**, complicates cookie auth, and is not a true APK product. |
| Static export | Many App Router features and dynamic segments make a full `output: 'export'` clinic app **non-trivial**; not configured today. |
| UI reuse | Could eventually host a Vite/SPA that imports `@healthcare-os/ui`. |
| Plugins | Strong ecosystem: Preferences, Biometrics, Filesystem, Background tasks (limited vs WorkManager). |

**Verdict:** Capacitor is viable as a **host for a dedicated SPA shell**, not as a drop-in wrap of current `apps/web` Next SSR.

### Option B — Native Android (Kotlin) + optional Compose UI

| Criterion | Assessment |
| --- | --- |
| Fit to repo | Clean API consumer via Bearer; no dependency on Next. |
| UI reuse | **Low** — rebuild screens; can share OpenAPI types only. |
| SQLCipher / Keystore / Biometric / WorkManager | **First-class.** |
| Cost | Highest engineering effort. |

**Verdict:** Best security/control for PHI offline; highest cost; consider for long-term if SPA+Capacitor proves insufficient.

### Option C — Hybrid (recommended for A1)

1. Extract/create `apps/mobile-web` (Vite + React 19) consuming `@healthcare-os/ui` + `packages/api-client`.  
2. Wrap with **Capacitor** for APK/AAB.  
3. Native plugins for Keystore, biometrics, SQLCipher bridge, WorkManager sync worker.  
4. Keep clinical authority on FastAPI.

## 3. Security building blocks (Android)

| Concern | Mechanism | Notes |
| --- | --- | --- |
| Encryption keys | **Android Keystore** (hardware-backed when available) | Do **not** store raw SQLCipher key in Preferences |
| Local DB | **SQLCipher** (or equivalent encrypted SQLite) | Per-tenant DB files or row-level tenant_id + wipe on revoke |
| Unlock | BiometricPrompt → unlock key alias | Fallback device credential; timeout re-lock |
| Tokens | Access short-lived in memory; refresh in Keystore-backed store | Align with server refresh rotation / reuse detection |
| Network | TLS only; optional cert pinning to API | Never log PHI |
| Background sync | **WorkManager** constraints (network, battery, storage) | Respect lease expiry; stop if revoked |

## 4. Auth flow (Android)

```
1. Login → POST /api/v1/auth/login with platform=android, device_id
2. Server returns Me + sets cookies (ignored) AND/OR JSON tokens for native
   (token-in-body endpoint or Accept header — NEW, must not weaken web cookies)
3. Store refresh via Keystore; keep access in memory
4. All API calls: Authorization: Bearer <access>, X-Tenant: <id>
5. Refresh via /api/v1/auth/refresh equivalent for bearer (may need explicit body/header variant)
```

**Gap vs today:** Login currently returns Me and sets **cookies only**. Native needs a documented **Bearer issuance** path (response body or separate token endpoint) without putting tokens in `localStorage` on web.

## 5. Offline authorization

- On successful online authz fetch, persist `AuthzLease` { permissions, tenant_ids, expires_at, device_id, signature? }.  
- Offline mutations allowed only if lease valid **and** operation in allowlist (e.g., draft notes yes; cross-tenant no; payments no).  
- Expired lease → read-only or lock app until online.

## 6. Packaging & distribution (summary)

See `platform-packaging-and-signing.md` — Play App Signing, upload key, CI secrets, ProGuard/R8, no PHI in crash logs.

## 7. Feasibility verdict — Android APK

| Gate | Status |
| --- | --- |
| Backend API reusable | **Yes** |
| Capacitor wrap of current Next app | **Not recommended** |
| Capacitor + SPA + `@healthcare-os/ui` | **Feasible** (recommended path) |
| Native Kotlin-only | Feasible, expensive |
| SQLCipher + Keystore + Biometric + WorkManager | **Standard; design-ready** |
| Ready to build APK in A0 | **No** — needs SPA shell ADR, Bearer device auth, sync MVP scope |

**Readiness for Android APK development:** **CONDITIONAL / NOT YET** — architecture approved direction is Hybrid Capacitor+SPA; implementation blocked on auth token contract + sync MVP definition.
