# Test evidence (Phase 1.2)

**Date:** 2026-11-25  
**Host:** Windows 10.0.26300  

## Toolchain

| Tool | Version |
|------|---------|
| Node | v24.11.1 |
| Python | 3.10.11 (venv) |
| rustc | 1.100.0 |
| cargo | 1.100.0 |
| Vite | 6.4.6 |
| Tauri CLI/crate | 2.x / 2.12.7 |

## Backend (PostgreSQL)

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_native_auth.py tests/api/test_auth_flow.py -q
```

**Result:** 17 passed  

| Case | Status |
|------|--------|
| Native login + workspace-context | PASS |
| Invalid password | PASS |
| Disabled account | PASS |
| Unauthorized tenant | PASS |
| Multiple workspaces | PASS |
| Refresh rotation + reuse | PASS |
| Logout revokes access | PASS |
| Browser cookie login / refresh / logout regression | PASS |
| Deactivated membership | PASS |

## Desktop frontend

```powershell
cd apps/desktop; npm run build
```

**Result:** PASS — `dist/` produced  

## DPAPI (Rust)

```powershell
cd apps/desktop/src-tauri; cargo test --lib
```

**Result:** 2 passed (`dpapi_round_trip_and_cleanup`, `invalid_ciphertext_fails`)

## Tauri package build

```powershell
cd apps/desktop; npx tauri build --debug
```

**Result:** PASS (build)

| Artifact | Path |
|----------|------|
| Debug EXE | `apps/desktop/src-tauri/target/debug/healthcare-os-desktop.exe` |
| NSIS setup | `apps/desktop/src-tauri/target/debug/bundle/nsis/Healthcare OS_0.1.0_x64-setup.exe` (~2.43 MiB) |

## Runtime GUI / live API through EXE

| Check | Status |
|-------|--------|
| EXE file exists | **PASS** |
| Interactive login UI against live FastAPI via EXE | **NOT TESTED** (no attended GUI session this phase) |
| End-to-end restore-after-restart via EXE | **NOT TESTED** |
| API auth lifecycle | **PASS** via pytest (same contracts the UI calls) |

## Legend applied

- Implemented and tested: native API, browser regression, Vite build, DPAPI unit tests, Tauri EXE **build**  
- Implemented but not runtime-tested: full desktop GUI auth loop  
- Not implemented: clinic modules, signing, offline
