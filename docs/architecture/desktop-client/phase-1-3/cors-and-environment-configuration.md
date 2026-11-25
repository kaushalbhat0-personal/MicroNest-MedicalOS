# CORS and environment configuration

## Desktop networking approach (Phase 1.3)

Authenticated API calls use **Rust `api_request`** with host allowlist = `HOS_API_BASE_URL`.

**Implication:** Packaged/desktop auth does **not** require browser CORS for Bearer calls. No production CORS change was made. No wildcard origins introduced.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `HOS_API_BASE_URL` | API origin (dev default `http://127.0.0.1:8000`) |
| `HOS_CHANNEL` | `development` \| `staging` (display + evidence) |
| `VITE_HOS_API_BASE_URL` / `VITE_HOS_CHANNEL` | Optional Vite overrides |
| `HOS_M3_AUTOLOGIN_EMAIL` / `HOS_M3_AUTOLOGIN_PASSWORD` | Synthetic evidence only |

Staging should use `https://…` API base. No production URL hardcoded.

## If browser fetch from WebView is needed later

Exact origins to add to **non-production** `ALLOWED_ORIGINS` (request approval before staging change):

- Dev Vite: `http://localhost:1420`  
- Tauri 2 WebView2 custom protocol (typical): `https://tauri.localhost` and/or `http://tauri.localhost`

Do **not** use `*` with credentials. Do **not** modify production CORS without explicit approval.

## Local API used for M3 evidence

- `ENV=dev` uvicorn on `127.0.0.1:8000`  
- Migration `0028` applied via Alembic  
- Existing local `.env` `ALLOWED_ORIGINS` left for Next web (`localhost:3000`); not relied upon by desktop Rust client
