# A1 — Android technical feasibility PoC report

**Verdict: FAIL** against acceptance criteria (encrypted DB + Android Keystore must be runtime-proven).

SPA / Capacitor direction remains architecturally sound (A0 confirmed); this PoC did **not** prove the security stack on device.

## Environment

| Tool | Result |
|------|--------|
| Node | v24.11.1 |
| Android SDK (partial under `%LOCALAPPDATA%\Android\Sdk`) | Present (build-tools, cmake, cmdline-tools) |
| `java` / `javac` | **NOT_FOUND** |
| `adb` on PATH | **NOT_FOUND** |
| Emulator / USB device | **NOT TESTED** (no adb) |
| Rust (irrelevant for A1) | NOT_FOUND |

Evidence: `experiments/native-client-poc/android/evidence/a1_environment.json`

## A1.1 Technology validation

### Comparison

| Approach | Routing | Auth | UI reuse | Offline startup | Verdict |
|----------|---------|------|---------|-----------------|---------|
| Capacitor + React + Vite SPA | Client router in SPA; no Next App Router | Bearer via secure store; mock proven for shape | Import `@healthcare-os/ui` (peer React 19) without Next server APIs | Bundle in `webDir` → works offline for cached assets | **Recommended** |
| Capacitor + Next static export | Blocked: App Router dynamic routes, SSR, rewrites, server-only proxy | Cookie model fights native | Couples to Next | Weak offline | **Reject for offline native** |
| Wrap Next SSR in WebView | Remote URL | Cookie / SSO fragile | Full web UI | **Fails** offline | **Reject** (explicit hard constraint) |
| Pure Kotlin Compose | Native nav | Bearer | Low UI reuse | Strong | Fallback if Capacitor plugins fail |

### UI package reuse

`packages/ui` is React 19 peer components (`Button`, fields, healthcare widgets). Reusable from a Vite SPA **if**:

- No imports of `next/*`, `apps/web/lib/*`, or server actions.
- WhatsApp helpers remain optional / disabled per product freeze (no automatic WhatsApp).

PoC SPA did **not** wire `@healthcare-os/ui` yet (isolation); reuse is **architecturally viable**, **NOT TESTED** in Capacitor WebView.

### Native plugins / lifecycle / background sync

| Topic | Assessment | Status |
|-------|------------|--------|
| Capacitor Network | Feasible for online/offline | NOT IMPLEMENTED in APK |
| App lifecycle | Standard Capacitor pause/resume; re-lock on background for PHI | Documented only |
| Background sync | WorkManager via custom plugin preferred over JS timers | NOT IMPLEMENTED |
| Upgrade / maintenance | SPA + Capacitor version matrix; native plugin churn | Medium cost |
| Biometric / app lock | BiometricPrompt over Keystore alias — feasible | NOT TESTED |

### Offline clinical writes

**Out of scope / disabled** this phase (hard constraint 10).

## A1.2 Minimal prototype — requirement map

| # | Requirement | Implementation | Test evidence | Status |
|---|-------------|----------------|---------------|--------|
| 1 | Android shell launches | Capacitor Android project **not** generated | — | **NOT IMPLEMENTED** |
| 2 | Login → test backend | SPA `App.tsx` + mock API `POST /auth/login` | SPA build PASS; login **NOT TESTED** in Android WebView (browser shape only) | **IMPLEMENTED** (SPA) / **NOT TESTED** (device) |
| 3 | Authenticated request | `GET /auth/me` with Bearer | Same | **IMPLEMENTED** / **NOT TESTED** (device) |
| 4 | Logout clears session | Clears in-memory token | Same | **IMPLEMENTED** / **NOT TESTED** (device) |
| 5 | SQLite opens | — | — | **NOT IMPLEMENTED** |
| 6 | Encrypted local storage (SQLCipher-compatible) | Notes only (`SqlCipherNotes.md`) | — | **NOT IMPLEMENTED** |
| 7 | Encryption key via Android Keystore | `KeystoreDbKeyStore.kt` source sample | No runtime | **IMPLEMENTED (source)** / **NOT TESTED** |
| 8 | Reopen encrypted DB after restart | Depends on 6–7 | — | **NOT TESTED** |
| 9 | Offline/online detection | `navigator.onLine` in SPA | Browser API only | **IMPLEMENTED** (SPA) / **NOT TESTED** (Capacitor Network) |
| 10 | Synthetic assigned patient offline | `fixtures/assigned-patients.json` rendered in SPA | Build embeds fixture | **PASS** (SPA static) / **NOT TESTED** (device offline) |

### Commands actually run

```text
cd experiments/native-client-poc/android/spa
npm install
npm run build
# vite 6.4.6 → dist/ PASS
```

Evidence: `a1_spa_build_evidence.json`

### What was NOT claimed

- Keystore round-trip is **not** proven.
- SQLCipher open/reopen is **not** proven.
- APK install / emulator launch is **not** proven.

## A1.3 Android security checks

| Check | Status | Notes |
|-------|--------|-------|
| No plaintext patient DB | **NOT TESTED** | No DB created on device |
| No secrets in source | **PASS** (PoC) | Mock password is synthetic fixture constant, not production secret; no JWT secret in client |
| No tokens in logs | **PASS** (SPA code review) | Comments forbid logging token |
| No PHI in notifications | **NOT IMPLEMENTED** | No notification path |
| No PHI in analytics/crash | **NOT IMPLEMENTED** | None wired |
| No unrestricted backup of patient data | **IMPLEMENTED** (guidance) | `backup_rules.xml` + recommend `allowBackup=false` — **NOT TESTED** on device |
| DB key not in ordinary prefs plaintext | **IMPLEMENTED** (design) | Kotlin wraps key; prefs hold ciphertext only — **NOT TESTED** |
| Logout / local cleanup | Design + SPA memory clear | Device wipe **NOT TESTED** |
| App lock / biometric feasibility | Feasible via Keystore user-auth flag | **NOT TESTED** |
| Revocation while permanently offline | Documented limitation | Device retains data until lease expiry; after expiry deny clinical cache; cannot push server revoke until online |

## Architecture recommendation (Android)

1. Keep **Capacitor + dedicated Vite SPA** (do not wrap Next SSR).
2. Block production Android work until a **lab machine** with JDK 17+, Android SDK platform-tools, emulator, runs Keystore + SQLCipher evidence harness.
3. Do not start full clinic Android app in parallel with Windows until backend device/lease contracts land (A3).

## Final A1 status

**FAIL** — acceptance requires runtime Keystore + encrypted DB evidence; unavailable on this workstation.
