# Native token API contract

Base path: `/api/v1/auth/native`

## POST `/login`

**Request**

```json
{
  "email": "user@example.com",
  "password": "…",
  "client_platform": "windows",
  "device_label": "optional",
  "client_instance_id": "optional-uuid"
}
```

**Response 200** — `NativeTokenResponse`

| Field | Description |
|-------|-------------|
| `access_token` | JWT access (`typ=access`, `sub`, `sid`, `jti`, `exp`) |
| `refresh_token` | `{session_id}.{secret}` — store via DPAPI only |
| `token_type` | `bearer` |
| `expires_in` | seconds (`ACCESS_TOKEN_MINUTES * 60`) |
| `id`, `email`, `display_name`, `is_platform_admin`, `email_verified` | profile |
| `tenants` | `{id, slug, name}[]` — workspace picker |
| `session_id` | current session UUID |
| `client_platform` | echoed platform |

**Does not** set `hos_access` / `hos_refresh` cookies.

**Errors:** 401 indistinct for bad credentials / inactive user; 422 validation.

## POST `/refresh`

**Request:** `{ "refresh_token": "{sid}.{secret}" }`  
**Response:** new `NativeTokenResponse` (rotated).  
**Reuse of old refresh:** 401; session family revoked.

## POST `/logout`

**Header:** `Authorization: Bearer <access>`  
**Response:** 204  
Revokes session row. Subsequent requests with that `sid` fail in `get_current_user` (immediate for access JWT bound to revoked session).

## Authenticated API calls

```
Authorization: Bearer <access_token>
X-Tenant: <tenant-uuid>   # required when multiple memberships
```

Permissions derived server-side via existing `require()` / `get_ctx`.

## Browser endpoints (unchanged)

| Endpoint | Behavior |
|----------|----------|
| `POST /auth/login` | Cookies + `MeResponse` (no tokens in JSON) |
| `POST /auth/refresh` | Cookie-only refresh |
| `POST /auth/logout` | Revoke + clear cookies |
