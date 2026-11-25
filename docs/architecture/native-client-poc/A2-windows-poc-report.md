# A2 — Windows desktop technical feasibility PoC report

**Verdict: CONDITIONAL PASS**

- **PASS:** DPAPI CurrentUser key wrap + encrypted-at-rest local DB + reopen after simulated restart + synthetic offline patient + logout wipe (runtime evidence).
- **NOT IMPLEMENTED:** Full Tauri 2 application shell / signed EXE / SQLCipher engine inside Tauri.
- **PASS (mock):** Login / me / logout Bearer flow against controlled mock API (tokens never logged).

## Environment

| Tool | Result |
|------|--------|
| Windows | win32 10.0.26300 |
| Python | 3.10.11 |
| cryptography | 50.0.2 |
| Node | v24.11.1 |
| rustc / cargo | **NOT_FOUND** → Tauri build blocked |
| Production code signing | Not attempted (constraint) |

## A2.1 Technology validation

| Topic | Finding |
|-------|---------|
| UI reuse | Same SPA strategy as Android: React + `@healthcare-os/ui` hosted in Tauri webview; avoid Next SSR |
| Packaging | Tauri 2 MSI/NSIS — **NOT TESTED** (no Rust toolchain) |
| Signing | Authenticode required for trust; not done in PoC |
| Auto-update | Tauri updater + signed artifacts — feasible; **NOT IMPLEMENTED** |
| Local DB | PoC: SQLite bytes sealed with AES-GCM; production: SQLCipher behind same `EncryptedDb` abstraction |
| Key protection | **DPAPI CryptProtectData / CryptUnprotectData (CurrentUser)** — **PASS** runtime |
| Background sync | Prefer per-user scheduled task / Tauri background; **NOT IMPLEMENTED** |
| Lifecycle | Documented; Tauri window lifecycle **NOT TESTED** |
| Resource / maintenance | Tauri lighter than Electron; Rust skill required |
| Electron comparison | Only material if Tauri SQLCipher/DPAPI bridge slips schedule; larger Chromium surface |

**DPAPI ≠ Android Keystore.** Shared abstraction: `SecureKeyStore` with platform impls; never call DPAPI from renderer JS with raw keys exposed.

### Windows profile change behavior

| Event | Effect |
|-------|--------|
| Same Windows user, app restart | DPAPI unwrap succeeds → DB readable (**proven**) |
| Different Windows user / profile | CryptUnprotectData fails → DB unreadable (by design) |
| Profile corruption / domain roaming edge cases | Keys may be unavailable; require re-onboarding + server re-auth |
| Admin copying sealed files to another machine | Useless without same user DPAPI context |

## A2.2 Minimal prototype — requirement map

| # | Requirement | Implementation | Evidence | Status |
|---|-------------|----------------|----------|--------|
| 1 | Desktop app launches | Python PoC process (not Tauri EXE) | Runtime script exit 0 | **CONDITIONAL PASS** (crypto host, not Tauri UI) |
| 2 | Login → test backend | `auth_and_session_poc.py` + mock API | `a2_windows_auth_evidence.json` | **PASS** |
| 3 | Authenticated request | `GET /auth/me` | same | **PASS** |
| 4 | Logout clears credentials | Memory clear + server session delete | same | **PASS** |
| 5 | SQLite opens | Temp SQLite build inside PoC | runtime | **PASS** |
| 6 | Encrypted local storage | AES-GCM file seal of SQLite bytes | `a2_windows_runtime_evidence.json` | **PASS** (not SQLCipher engine) |
| 7 | Key via DPAPI | `CryptProtectData` wrap of DEK | same | **PASS** |
| 8 | Readable after restart | Delete in-memory DEK; unwrap from disk; decrypt | same | **PASS** |
| 9 | Offline/online detectable | urllib probe + flag | `online_offline_detectable=PASS` | **PASS** |
| 10 | Synthetic patient offline | Row `syn-patient-001` after decrypt | same | **PASS** |

### Exact commands

```powershell
python experiments/native-client-poc/windows/dpapi_encrypted_db_poc.py
# All checks PASS — evidence/a2_windows_runtime_evidence.json

node experiments/native-client-poc/shared/mock-api/server.mjs
python experiments/native-client-poc/windows/auth_and_session_poc.py
# All checks PASS — evidence/a2_windows_auth_evidence.json
```

### Runtime check dump (2026-11-25)

```
dpapi_protect=PASS
dek_not_plaintext_on_disk=PASS
encrypted_db_write=PASS
no_plaintext_phi_on_disk=PASS
dpapi_unprotect_after_restart=PASS
encrypted_db_read_after_restart=PASS
offline_synthetic_patient_visible=PASS
logout_wipes_local_artifacts=PASS
online_offline_detectable=PASS
```

## A2.3 Windows security checks

| Check | Status | Notes |
|-------|--------|-------|
| No plaintext patient DB | **PASS** | Patient display name absent from sealed file bytes |
| No secrets in source | **PASS** | No production secrets; synthetic PoC password only in mock path |
| No PHI in logs | **PASS** | Script prints check names only |
| No PHI in crash reports | **NOT IMPLEMENTED** | No crash reporter |
| No unrestricted backup of local patient data | **CONDITIONAL** | Sealed file still backup-able by user/OS; mitigate with ACL + BitLocker guidance + wipe on logout; full backup policy **NOT TESTED** |
| Encryption key not plaintext | **PASS** | DEK only as DPAPI blob on disk |
| Logout / session cleanup | **PASS** (PoC wipe) | Deletes sealed DB + wrap file |
| Secure update feasibility | Documented | **NOT IMPLEMENTED** |
| Account-bound key protection | **PASS** | DPAPI CurrentUser |

## Honesty bar

- SQLCipher **engine** was **not** used; encrypted-at-rest + DPAPI wrap **was** proven — sufficient for A2 acceptance language on “encrypted database and DPAPI/key-protection integration,” with explicit follow-up to swap seal for SQLCipher under the same abstraction.
- Tauri packaging remains a **separate** engineering gate (install Rust, scaffold `apps/desktop`).

## Final A2 status

**CONDITIONAL PASS** — DPAPI + encrypted local store proven; Tauri shell / signing / SQLCipher engine / production auth body tokens remain open.
