# Phase 1.2 — Native Authentication + Windows Desktop Foundation

**Date:** 2026-11-25  
**Branch:** `release/p3-7b-staging` (no commit/push)  
**Scope:** B0 design, FastAPI native JSON auth, Tauri 2 shell, DPAPI refresh store  
**Out of scope:** Clinic modules, offline DB, signing, deploy

## Verdicts

| Area | Verdict |
|------|---------|
| Overall | **CONDITIONAL PASS** |
| B0 design | **PASS** |
| Native auth API + PostgreSQL tests | **PASS** |
| Browser cookie regression | **PASS** |
| Tauri shell source + Vite build | **PASS** |
| DPAPI in Rust (unit tests) | **PASS** |
| Tauri EXE / NSIS **build** | **PASS** (`healthcare-os-desktop.exe` + setup) |
| EXE interactive login vs live API | **NOT TESTED** |
| Production readiness | **FAIL** (not claimed) |

## Documents

1. [native-auth-implementation.md](./native-auth-implementation.md)  
2. [native-token-api-contract.md](./native-token-api-contract.md)  
3. [tauri-desktop-foundation.md](./tauri-desktop-foundation.md)  
4. [dpapi-token-storage.md](./dpapi-token-storage.md)  
5. [security-validation.md](./security-validation.md)  
6. [test-evidence.md](./test-evidence.md)  
7. [known-limitations.md](./known-limitations.md)  

B0 design: `docs/architecture/native-auth/B0-native-auth-design.md`

## Key paths

| Path | Role |
|------|------|
| `backend/app/api/v1/native_auth.py` | Native login/refresh/logout |
| `backend/alembic/versions/0028_native_session_metadata.py` | Session metadata columns |
| `apps/desktop/` | Tauri 2 + React/Vite clinic shell |
| `apps/desktop/src-tauri/src/secure_store.rs` | DPAPI SecureTokenStore |

## Exact next milestone

**M3/M4** from Phase 1.1 roadmap: role-based nav + dashboard against staging API with a verified `tauri dev` runtime session — after EXE launch evidence is captured on a machine with WebView2 + MSVC.
