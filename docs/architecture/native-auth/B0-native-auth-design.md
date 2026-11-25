# B0 — Native authentication design (Phase 1.2)

**Date:** 2026-11-25  
**Branch:** `release/p3-7b-staging` @ `293dc66`  
**Status:** APPROVED FOR IMPLEMENTATION (no major blocker)

## Evidence inspected

| Area | Location | Finding |
|------|----------|---------|
| Browser login | `api/v1/auth.py` | Cookies via `issue_session_pair`; `MeResponse` only |
| Refresh | `auth.py` + `identity.service.rotate_session` | Cookie-only; rotation + reuse → family revoke |
| JWT | `platform/security/tokens.py` | HS256; claims `typ=access`, `sub`, `sid`, `iat`, `exp`, `jti` |
| Validation | `api/deps.py` | Bearer **or** cookie; session row must be active (revoked → 401) |
| Refresh storage | `sessions.refresh_hash` | SHA-256 only; never plaintext |
| Cookies | `platform/security/cookies.py` | HttpOnly, SameSite=Lax, Secure flag from settings |
| Schema | `identity/models.py` Session | No `device_id` / platform yet |
| Audit | `AuthEvent` | login_success/failed, session_refreshed, session_reuse_detected, session_revoked |

**Major blocker?** None for an additive native JSON contract reusing the same `Session` + JWT machinery.

---

## A. Browser compatibility (unchanged)

| Behavior | Rule |
|----------|------|
| `POST /api/v1/auth/login` | Still sets HttpOnly cookies; still returns `MeResponse` without tokens |
| `POST /api/v1/auth/refresh` | Still cookie-only |
| `POST /api/v1/auth/logout` | Still revokes session + clears cookies |
| Same-origin proxy / cookie attrs | Untouched |
| localStorage | **Never** used for browser auth |

---

## B. Native authentication (additive)

New routes under `/api/v1/auth/native/*` that **reuse** `authenticate`, `create_session`, `rotate_session`, `revoke_session`, and `create_access_token`.

| Endpoint | Purpose |
|----------|---------|
| `POST /auth/native/login` | Credentials → access + refresh JSON + profile + tenants |
| `POST /auth/native/refresh` | Body refresh → rotated access + refresh JSON |
| `POST /auth/native/logout` | Bearer access → revoke current session (no cookie dependency) |

No parallel user table. No parallel RBAC.

---

## C. Token security

| Property | Design |
|----------|--------|
| Access algorithm | Existing `JWT_ALGORITHM` (default **HS256**) with `JWT_SECRET` |
| Issuer / audience | **Not present today** — do not invent without migration of web tokens; defer `iss`/`aud` to a later hardening ADR |
| Subject | `sub` = user UUID (existing) |
| Type | `typ` = `"access"` (existing; reject others) |
| Expiry | `ACCESS_TOKEN_MINUTES` (default 10) |
| Token id | `jti` = uuid7 (existing) |
| Session bind | `sid` = session UUID; **every** request loads session — revoked sessions fail immediately |
| Refresh generation | `secrets.token_urlsafe(48)` (existing) |
| Refresh persistence | SHA-256 hex in `sessions.refresh_hash` (existing) |
| Wire format (native) | Refresh presented as `{session_id}.{secret}` (same as cookie value today) |
| Rotation | Existing `rotate_session` (mark old `rotated`, new row same `family_id`) |
| Replay / reuse | Existing family revoke + `session_reuse_detected` |
| Concurrent refresh | Rely on unique `refresh_hash` + transactional session; first writer wins; loser hits reuse/mismatch path |

**Access after logout:** Because `get_current_user` checks `sessions.revoked_at`, access JWTs bound to that `sid` are **rejected immediately** after logout/revoke (not merely at JWT exp). Document this as implemented behavior.

---

## D. Workspace selection

1. Native login returns `tenants[]` (id, slug, name) — same as `MeResponse`.  
2. Client selects a tenant UUID and sends `X-Tenant` on subsequent calls.  
3. Server `get_ctx` validates membership and loads permissions from DB roles — **never** from client-supplied roles.  
4. Optional: client may call `GET /tenants/{id}/workspace-context` after login for permission introspection (existing).

---

## E. Device / session association (online-first minimum)

| Field (new, nullable) | Purpose |
|-----------------------|---------|
| `client_platform` | `windows` \| `web` \| null (legacy web) |
| `device_label` | Optional human label (e.g. hostname), max 120, no secrets |
| `client_instance_id` | Optional opaque UUID string from client install — **not** cryptographic PoP |

**Deferred (risk accepted for v1):** Device-bound public-key proof-of-possession, attestation, offline leases, device registry APIs. Stolen refresh still mitigated by rotation + reuse detection + DPAPI on disk.

---

## F. Audit actions (native)

Reuse existing actions where possible; add platform-tagged variants only if needed for filtering:

- `login_success` / `login_failed` (existing; native uses same after authenticate)  
- `session_refreshed` / `session_reuse_detected` / `session_revoked`  
- Optional metadata via `user_agent` containing `HealthcareOS-Desktop/...` — no secrets in audit payloads

---

## G. Implementation order

1. Alembic: session metadata columns  
2. Service: extend `create_session` kwargs  
3. Schemas + native routes  
4. Tests (PostgreSQL) including browser regression  
5. Desktop client + DPAPI store  

**B0 GATE: PASS — proceed to implementation.**
