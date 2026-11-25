# M3 — Runtime authentication report

**Verdict: PASS**

## What was proven (actual Windows EXE)

Process `healthcare-os-desktop.exe` (debug build) against local FastAPI `http://127.0.0.1:8000`:

1. Launch  
2. Native login (`POST /api/v1/auth/native/login`)  
3. Workspace selection (single-tenant auto-select)  
4. `/api/v1/auth/me`  
5. Refresh rotation via DPAPI-stored refresh  
6. `/me` after refresh  
7. Logout + DPAPI clear  
8. Re-login for interactive shell  

Evidence: `evidence/m3_runtime_evidence.json` (no tokens).

| Check | Result |
|-------|--------|
| login | true |
| workspace_selected | true |
| me_email_matches | true |
| refresh DPAPI envelope after login | exists, ciphertext JSON, no plaintext token shape |
| refresh_rotated | true |
| me_after_refresh | true |
| logout_cleared_dpapi | true |
| access_in_memory_after_logout | true |

## Implementation notes

- HTTP to the API is performed by **Rust** (`api_request`) with **host allowlisting** to `HOS_API_BASE_URL` — desktop does not depend on browser CORS for auth.  
- Access token remains in renderer memory only.  
- Refresh token only via DPAPI `SecureTokenStore`.  
- Autologin used **only** for synthetic evidence via `HOS_M3_AUTOLOGIN_*` env (not shipped as default UX).

## Synthetic account

`desktop.poc@example.com` / seed script `scripts/_p13_seed_desktop_user.py` — not production PHI.
