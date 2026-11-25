# Known limitations (Phase 1.2)

1. **No clinic feature modules** — shell placeholder only.  
2. **JWT iss/aud not added** — preserves compatibility with existing web tokens.  
3. **Device PoP deferred** — `client_instance_id` is opaque association only.  
4. **CORS** — desktop WebView origins must be listed in `ALLOWED_ORIGINS` for cross-origin API (e.g. `http://localhost:1420`).  
5. **WebView2 / MSVC** required for packaged EXE on target PCs.  
6. **Unsigned builds** — not for clinic distribution.  
7. **Browser login `tenants[]` under RLS** — historical quirk without `app.user_id`; native path sets actor before listing tenants. Browser `/me` still works after cookie auth.  
8. **No offline** — intentional.  
9. **Full GUI E2E** may be incomplete if `tauri dev` was not run against a live API in this session — backend + DPAPI + Vite are independently proven.
