# Native authentication implementation

## What changed

| Change | Detail |
|--------|--------|
| Migration `0028_native_session_metadata` | `sessions.client_platform`, `device_label`, `client_instance_id` (nullable) + index |
| Model / service | `create_session` + `rotate_session` preserve platform metadata |
| Routes | `backend/app/api/v1/native_auth.py` mounted in `router.py` |
| Schemas | `NativeLoginRequest`, `NativeRefreshRequest`, `NativeTokenResponse` |
| Browser paths | **Unchanged** (`/auth/login`, `/refresh`, cookie logout) |

## Behavior notes

- Refresh secrets stored **only** as SHA-256 (`refresh_hash`).
- Access JWT validation still loads session; **revoked sessions reject access immediately**.
- Native login sets `app.user_id` before `tenant_options` so RLS returns memberships.
- Rate limits reuse existing login/refresh IP and account limiters.
- Audit: existing `login_success` / `login_failed` / `session_refreshed` / `session_reuse_detected` / `session_revoked`.

## Tests

`tests/api/test_native_auth.py` + existing `tests/api/test_auth_flow.py` against real PostgreSQL (`TEST_*_DATABASE_URL`).

Result (2026-11-25): **17 passed** (10 native + 7 browser flow).
