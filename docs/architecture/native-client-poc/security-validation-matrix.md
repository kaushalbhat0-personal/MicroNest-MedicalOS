# Security validation matrix (A1 / A2 / A3)

Legend: **PASS** | **CONDITIONAL PASS** | **FAIL** | **NOT TESTED** | **NOT IMPLEMENTED**

## Local data protection

| Control | Android | Windows | Evidence |
|---------|---------|---------|----------|
| No plaintext patient DB on disk | NOT TESTED | **PASS** | Windows sealed file lacks display_name plaintext |
| Encrypted storage | NOT IMPLEMENTED (SQLCipher) | **PASS** (AES-GCM seal) | `a2_windows_runtime_evidence.json` |
| OS-bound key protection | NOT TESTED (Keystore sample only) | **PASS** (DPAPI) | same |
| Key not in ordinary prefs/plaintext file | Design PASS / runtime NOT TESTED | **PASS** | dek.dpapi ≠ raw key |
| Logout wipes local artifacts | NOT TESTED on device | **PASS** | PoC deletes seal + wrap |
| Backup restrictions | Guidance XML only | CONDITIONAL (ACL/BitLocker policy) | `backup_rules.xml` |

## Secrets & telemetry

| Control | Android SPA | Windows PoC | Notes |
|---------|-------------|-------------|-------|
| No production secrets in source | **PASS** | **PASS** | Synthetic PoC password only |
| No tokens in logs | **PASS** (code) | **PASS** | Auth evidence omits token values |
| No PHI in notifications | NOT IMPLEMENTED | NOT IMPLEMENTED | — |
| No PHI in analytics / crash | NOT IMPLEMENTED | NOT IMPLEMENTED | Do not enable until scrubbing policy exists |
| Logging redaction server-side | Existing FastAPI redacts token keys | N/A | `logging_setup.py` |

## AuthN / AuthZ

| Control | Status | Notes |
|---------|--------|-------|
| Web cookie auth unchanged | **PASS** (not modified) | Hard constraint |
| Second auth system introduced? | **PASS** (none) | Mock is PoC-only |
| Native Bearer against production login JSON | **FAIL** | Cookies only today |
| Bearer accepted by deps | **PASS** | `deps.py` |
| Device binding / revoke | NOT IMPLEMENTED | A3 |
| Authorization lease | NOT IMPLEMENTED | A3 |
| Offline clinical writes disabled | **PASS** (phase constraint) | Enforced by not building write sync |

## Platform-specific risks

| Risk | Status | Mitigation |
|------|--------|------------|
| Permanent offline after revoke | Documented limitation | Lease expiry caps window; wipe on next online |
| Windows profile change | Documented | DPAPI fails → re-enroll |
| Android Keystore not hardware-backed on some devices | NOT TESTED | Detect StrongBox; policy |
| User-level file copy of sealed DB (Windows) | Residual | Useless without DPAPI context; still treat as sensitive |
| Capacitor WebView XSS → key exfil | NOT TESTED | Keep keys in native plugin; CSP; no key in JS |

## Acceptance mapping

| Gate | Required | Result |
|------|----------|--------|
| A1 encrypted DB + Keystore runtime | Mandatory for A1 PASS | **FAIL** |
| A2 encrypted DB + DPAPI runtime | Mandatory for A2 PASS | **PASS** (crypto); overall CONDITIONAL (no Tauri) |
| Shared contracts implemented | Mandatory for shared PASS | **FAIL** (proposal only) |
| No production PHI | Mandatory | **PASS** (synthetic only) |
| No production deploy mutation | Mandatory | **PASS** |
