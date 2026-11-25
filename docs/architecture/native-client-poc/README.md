# Native Client Feasibility PoCs (A1 + A2 + A3)

**Phase:** A1/A2 technical feasibility — stop before full application development  
**Date:** 2026-11-25  
**Constraint:** No commit, push, deploy, PHI, Docker, or production config changes

## Overall verdict

**NOT READY for full dual-client development.**

| Track | Verdict | One-line reason |
|-------|---------|-----------------|
| A1 Android | **FAIL** (acceptance) | No runtime evidence of Keystore + encrypted DB (no JDK / adb / device) |
| A2 Windows | **CONDITIONAL PASS** | DPAPI + encrypted-at-rest SQLite **runtime-proven**; Tauri/SQLCipher shell not built |
| A3 Shared contracts | **FAIL as implementation** / **PASS as audit+proposal** | Device/lease/outbox APIs **missing** on FastAPI; contracts drafted |
| Dual full build now | **Do not** | Sequence Windows crypto path → backend device contracts → Android lab with JDK/emulator |

## Documents in this folder

1. [A1-android-poc-report.md](./A1-android-poc-report.md)
2. [A2-windows-poc-report.md](./A2-windows-poc-report.md)
3. [A3-shared-client-contract-audit.md](./A3-shared-client-contract-audit.md)
4. [security-validation-matrix.md](./security-validation-matrix.md)
5. [technology-comparison.md](./technology-comparison.md)
6. [implementation-roadmap.md](./implementation-roadmap.md)
7. [known-limitations.md](./known-limitations.md)

## Experiment code (isolated)

```
experiments/native-client-poc/
  android/          # Vite SPA + Kotlin Keystore sample (not runtime-tested)
  windows/          # DPAPI + AES-GCM PoC + auth client (runtime-tested)
  shared/
    mock-api/       # Controlled Bearer mock — not production FastAPI
    contracts/      # Device/lease/outbox proposal
```

## Reproduction (exact)

### Windows crypto + auth

```powershell
# Terminal 1
node experiments/native-client-poc/shared/mock-api/server.mjs

# Terminal 2
python -c "import cryptography; print(cryptography.__version__)"   # expect 50.0.2
python experiments/native-client-poc/windows/dpapi_encrypted_db_poc.py
python experiments/native-client-poc/windows/auth_and_session_poc.py
```

Evidence:

- `experiments/native-client-poc/windows/evidence/a2_windows_runtime_evidence.json`
- `experiments/native-client-poc/windows/evidence/a2_windows_auth_evidence.json`

### Android SPA build only

```powershell
cd experiments/native-client-poc/android/spa
npm install
npm run build
```

Evidence: `experiments/native-client-poc/android/evidence/a1_spa_build_evidence.json`  
Keystore/SQLCipher: **NOT TESTED** — see `a1_environment.json`.

## Status legend

| Status | Meaning |
|--------|---------|
| PASS | Implemented and runtime-proven with evidence |
| CONDITIONAL PASS | Core claim proven; named blockers remain |
| FAIL | Acceptance criterion not met |
| NOT TESTED | Code/interface may exist; no runtime proof |
| NOT IMPLEMENTED | Not built in this phase |

## Hard stops observed

1. Production `/api/v1/auth/login` returns **cookies only** (`MeResponse`); does not emit Bearer in JSON — native clients need a deliberate native token response path (same session/JWT system, not a second auth system).
2. No `devices`, leases, or device-outbox endpoints on backend.
3. Android Keystore cannot be claimed proven without device/emulator + JDK.
4. Tauri 2 EXE not built (`rustc`/`cargo` absent on this workstation).
