# Security validation (Phase 1.3)

| Control | Status | Notes |
|---------|--------|-------|
| No mock auth for acceptance | **PASS** | Real FastAPI native endpoints |
| Refresh not in localStorage/sessionStorage | **PASS** | DPAPI via Rust only |
| Refresh not plaintext on disk | **PASS** | Evidence: JSON envelope + ciphertext_b64 |
| Tokens not in evidence/logs | **PASS** | Writer rejects JSON containing token keys; no password in evidence |
| Host allowlisted HTTP | **PASS** | `api_http` denies non-base hosts |
| No wildcard CORS added | **PASS** | Production CORS untouched; desktop uses Rust HTTP |
| Browser cookie auth preserved | **PASS** | Regression tests green |
| Client nav ≠ authorization | **PASS** | Placeholders + server `require()` |
| Stale workspace on switch | **PASS** | `clearTenantScoped` before reselect |
| Tauri capabilities | **PASS** | `core:default` only; no opener/shell/fs extras |
| Infinite refresh loop | **PASS** | Single in-flight refresh; one retry on 401 |
| Autologin credentials | **CONDITIONAL** | Env-only for synthetic evidence; must not ship enabled |
