# DPAPI token storage

## Interface

Rust module `secure_store` + Tauri commands:

| Operation | Command |
|-----------|---------|
| storeRefreshToken | `store_refresh_token` |
| retrieveRefreshToken | `retrieve_refresh_token` |
| deleteRefreshToken | `delete_refresh_token` |
| clearSession | `clear_session` |

Path: `%LOCALAPPDATA%\HealthcareOS\credentials\refresh.dpapi`  
Contents: JSON envelope `{ v: 1, ciphertext_b64 }` where ciphertext is **DPAPI CurrentUser** (`CryptProtectData`).

Access tokens: **memory only** (React module variable).

## Tests (Rust, Windows)

```
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --lib
```

| Test | Result |
|------|--------|
| `dpapi_round_trip_and_cleanup` | **PASS** |
| `invalid_ciphertext_fails` | **PASS** |

Evidence: plaintext refresh string absent from disk blob; retrieve after protect; clear → Missing.

## Limitations / recovery

| Event | Behavior |
|-------|----------|
| Same Windows user, app restart | Unprotect succeeds → session restore via `/auth/native/refresh` |
| Different Windows user / broken profile | Unprotect fails → re-login |
| Logout | Deletes credential file |
| Stolen disk copy | Useless without same user DPAPI context; still treat as sensitive |

**Not claimed:** Full Tauri GUI path exercising invoke from WebView was separately verified only if `tauri dev` runtime evidence exists (see test-evidence).

Prior Python PoC (`experiments/native-client-poc/windows`) remains valid supporting evidence for CryptProtectData; Phase 1.2 uses **Rust in `apps/desktop`**, not a mock.
