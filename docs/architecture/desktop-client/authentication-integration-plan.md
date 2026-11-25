# Authentication integration plan (Phase 1.1)

**Implementation in this phase:** none.  
**Goal:** document exact dependencies before desktop login work.

---

## 1. Current production behavior (verified)

| Step | Behavior | Evidence |
|------|----------|----------|
| Login | `POST /api/v1/auth/login` → `MeResponse` + **Set-Cookie** `hos_access` / `hos_refresh` | `backend/app/api/v1/auth.py`, `_shared.py` |
| JSON tokens | **Not returned** | `identity/schemas.py` — responses must not contain tokens |
| Refresh | `POST /api/v1/auth/refresh` reads **refresh cookie only** | `auth.py` |
| Authenticated calls | Cookie **or** `Authorization: Bearer` (Bearer preferred) | `deps.py` `_read_access_token` |
| Logout / me / sessions | `account.py` via `get_current_user` | exists |
| Session model | `sessions` row with `refresh_hash`; **no `device_id`** | `identity/models.py` |
| Web path | HttpOnly cookies + same-origin proxy (P3.7D uncommitted helpers) | web-only |

**A1/A2 mock API** returned Bearer in JSON for shape testing only — **not** production.

---

## 2. Native proposal (aligned with A3; online-first subset)

Preserve browser cookies. Add a **native response mode** on the same session/JWT system:

1. Client sends `client_platform: "windows"` (and optional `device_id` after registration).  
2. Server still creates `Session` + access JWT (`sub`, `sid`) with existing TTLs.  
3. Response includes `access_token` + `refresh_token` (or `session_id.secret`) **for native only**.  
4. Optionally omit Set-Cookie for native User-Agent / platform flag.  
5. Refresh endpoint accepts refresh in **JSON body or Authorization** for native; cookie path unchanged for web.  
6. Store refresh via **DPAPI / Credential Manager** (A2 PoC pattern); access in memory.  
7. API calls: `Authorization: Bearer` + `X-Tenant`.

**Do not** introduce a parallel OAuth/IdP unless product later requires it.  
**Do not** use local mock auth as a substitute in implementation phases.

---

## 3. Dependencies before desktop login can be implemented

| ID | Dependency | Blocker? |
|----|------------|----------|
| B0 | Backend: native login/refresh JSON token contract + tests | **Yes** |
| B0b | CORS already allows `Authorization` / `X-Tenant` — verify desktop origin/ whitelisting policy for Tauri (`tauri://` / `http://localhost` during dev) | **Yes** (config) |
| B1 | Optional: `sessions.device_id` + register/revoke for session hygiene | Recommended, not strictly required for online-first MVP |
| C0 | Desktop `CredentialStore` Rust command (DPAPI) | **Yes** for secure refresh persistence |
| C1 | Typed `api-client` bearer adapter | **Yes** |
| C2 | Workspace-context fetch for permissions | Uses existing API — **No** backend change |
| — | Offline lease / device outbox | **No** for v1 online-first |
| — | Local patient DB | **No** for v1 |

---

## 4. Desktop login UX (spec only)

1. Email/password form (same credentials as web).  
2. On success: store refresh securely; keep access in memory; load tenants.  
3. If multiple tenants → workspace picker.  
4. Load `workspace-context` → filter nav.  
5. On 401: attempt refresh once; else login screen.  
6. Logout: `POST /auth/logout` + clear store.

---

## 5. Security requirements

- Never log tokens or PHI.  
- Never put refresh in `localStorage` / plain files.  
- Clear credentials on logout and uninstall guidance.  
- Align access TTL with `ACCESS_TOKEN_MINUTES`; refresh with `REFRESH_TOKEN_DAYS`.  
- Session revoke from `/sessions` must invalidate desktop on next refresh.

---

## 6. Acceptance for a future auth milestone (not Phase 1.1)

- Web cookie login still passes existing Playwright.  
- Desktop can obtain access without cookie jar.  
- Refresh works without browser cookies.  
- Logout revokes server session and clears DPAPI blob.  
- No second user store or permission engine.
