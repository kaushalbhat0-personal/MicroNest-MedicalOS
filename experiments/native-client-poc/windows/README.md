# A2 Windows PoC (experimental)

## What runs on this machine

| Artifact | Command | Result |
|----------|---------|--------|
| DPAPI + AES-GCM sealed SQLite | `python dpapi_encrypted_db_poc.py` | PASS (see `evidence/a2_windows_runtime_evidence.json`) |
| Auth/session vs mock API | Start `../shared/mock-api/server.mjs`, then `python auth_and_session_poc.py` | PASS |
| Full Tauri 2 shell | — | **NOT IMPLEMENTED** (`rustc`/`cargo` missing) |
| SQLCipher engine | — | **NOT USED** (file-level AES-GCM seal demonstrates encrypted-at-rest + DPAPI wrap) |

## Production direction (unchanged from A0)

Tauri 2 + React SPA + SQLCipher + DPAPI/Credential Manager behind `SecureKeyStore`.
