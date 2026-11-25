# Security validation (Phase 1.2)

| Control | Status | Evidence |
|---------|--------|----------|
| Browser cookie auth unchanged | **PASS** | `test_auth_flow` + native regression tests |
| No parallel user/RBAC system | **PASS** | Reuses identity sessions + `require()` |
| Refresh not plaintext on disk | **PASS** | Rust DPAPI unit test |
| Refresh not in localStorage | **PASS** | Code review — SecureTokenStore → invoke only |
| Tokens not logged | **PASS** | Code review (no console.log of tokens) |
| Access rejected after logout | **PASS** | `test_native_logout_revokes_access` |
| Refresh reuse kills family | **PASS** | `test_native_refresh_rotation_and_reuse` |
| Cross-tenant denied | **PASS** | `test_native_unauthorized_tenant` |
| Deactivated membership denied | **PASS** | `test_revoked_membership_cannot_use_tenant` |
| Disabled user login denied | **PASS** | `test_native_disabled_account` |
| Opener / shell IPC removed | **PASS** | capabilities = `core:default` only |
| No patient data local store | **PASS** | Online-first; only refresh credential file |
| Production signing | **NOT IMPLEMENTED** | Out of scope |
| iss/aud JWT claims | **NOT IMPLEMENTED** | Deferred (B0) |
| Device crypto PoP | **NOT IMPLEMENTED** | Deferred; risk accepted |

## Access-token revocation honesty

Session revoke marks `sessions.revoked_at`. `get_current_user` loads `sid` and rejects revoked sessions → **access JWTs fail on next authenticated request**, not merely after JWT `exp`.
