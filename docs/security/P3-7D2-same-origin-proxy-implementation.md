# P3.7D.2 — Same-Origin API Proxy Implementation

**Verdict: PASS** — implementation complete; P3.7D.3 Preview browser verification **17/17 PASS**  
(see `docs/deployment/P3-7D3-same-origin-preview-verification.md`).

Date: 2026-11-25  
Audit: `docs/security/P3-7D1-same-origin-auth-architecture-audit.md`  
Branch: `release/p3-7b-staging` (local changes; **not committed**; Preview deployed via CLI archive)  
Production `main`: **untouched**  
Verified Preview: `https://micro-nest-medical-3jjkc67ds-kaushal-bhats-projects.vercel.app` (`dpl_G62cQNjWWFzRdwmxSW5MJDm8fJZG`)

---

## 1. Audit reference

P3.7D.1 recommended **Option A**: Vercel same-origin rewrite  
`/api/:path*` → `https://micronest-medicalos.onrender.com/api/:path*`  
with relative browser fetch, keep `SameSite=Lax` / HttpOnly / Secure, no `SameSite=None`, no token localStorage.

This phase implements that design. Fallback Route Handler proxy was **not** required (rewrite compiles into `.next` routes manifest).

---

## 2. Architecture implemented

```
Browser (Vercel Preview or local Next)
  fetch("/api/v1/...", { credentials: "include" })   // same-origin
       │
       ▼
Next.js rewrite (fixed allowlist upstream)
  /api/:path*  →  {API_REWRITE_UPSTREAM}/api/:path*
       │
       ▼
FastAPI on Render (or local uvicorn)
  Sets hos_access / hos_refresh (HttpOnly; Secure; SameSite=Lax; host-only)
```

- Upstream destination is **not** client-controlled.
- Allowlist: `http://127.0.0.1:8000`, `http://localhost:8000`, `https://micronest-medicalos.onrender.com`.
- Default when `API_REWRITE_UPSTREAM` unset: `http://127.0.0.1:8000`.
- `Cache-Control: private, no-store…` applied to `/api/:path*` on the Next host.

---

## 3. Files changed

| File | Change |
| --- | --- |
| `apps/web/next.config.mjs` | `rewrites()` + `/api` no-store headers |
| `apps/web/lib/apiProxyConfig.mjs` | Allowlist, rewrite rules, cookie hardening asserts |
| `apps/web/lib/apiBase.ts` | Same-origin base URL resolution + `apiUrl` |
| `apps/web/lib/api.ts` | Uses `apiUrl()`; relative by default |
| `apps/web/lib/apiBase.test.ts` | Client base/path tests |
| `apps/web/lib/apiProxyConfig.test.ts` | Proxy security + cookie attribute tests |
| `.env.example` | Documents `API_REWRITE_UPSTREAM` / same-origin mode |

**Not changed:** FastAPI cookie/CSRF/CORS code, `main` branch, Render env (deployment deferred), no Route Handler fallback.

---

## 4. Request / response flow

1. UI calls `api.post("/api/v1/auth/login", …)` → `fetch("/api/v1/auth/login", { credentials: "include" })`.
2. Next rewrite proxies to `{upstream}/api/v1/auth/login` (method, query, body forwarded by platform).
3. FastAPI authenticates, returns JSON + two `Set-Cookie` headers (unchanged attributes).
4. Browser stores cookies for the **Next/Vercel host** (host-only; Path `/api` / `/api/v1/auth`).
5. Subsequent `fetch("/api/v1/auth/me", { credentials: "include" })` sends `hos_access` same-site.
6. Logout `POST /api/v1/auth/logout` clears cookies via upstream `delete_cookie` (same paths).

Build evidence (local production build with `API_REWRITE_UPSTREAM=https://micronest-medicalos.onrender.com`):

```text
.next/routes-manifest.json
  source: /api/:path*
  destination: https://micronest-medicalos.onrender.com/api/:path*
```

---

## 5. Cookie behavior

| Attribute | Policy | Proxy role |
| --- | --- | --- |
| HttpOnly | required | Forward only — not rewritten |
| Secure | required when `COOKIE_SECURE=true` | Forward only |
| SameSite | **Lax only** | Forward only; `None` forbidden |
| Domain | unset (host-only) | Must stay unset so Preview host owns cookie |
| Path | `/api`, `/api/v1/auth` | Matches proxied paths |

Unit tests assert these attributes on representative `Set-Cookie` strings (login + logout shapes). Live multi-`Set-Cookie` passthrough through Vercel edge is **pending Preview redeploy proof**.

---

## 6. Origin / CSRF findings

| Topic | Finding |
| --- | --- |
| CSRF tokens | **None** in codebase — not invented by this proxy |
| CSRF control | `SameSite=Lax` on first-party cookies after same-origin migration |
| CORS | Still exact-origin allowlist on Render; keep Preview origin until verified |
| `X-Forwarded-*` | FastAPI auth uses cookie JWT / Bearer only (`deps.get_current_user`); no auth via forwarded IP/host |
| Separate CSRF token project | Deferred — do not add decorative CSRF; design properly before any `SameSite=None` |

---

## 7. Security protections

- Closed upstream allowlist (rejects `evil.example.com`, link-local metadata IPs, etc.).
- No open proxy / no client-selected destination.
- No secrets in `NEXT_PUBLIC_*` for rewrite (use server-only `API_REWRITE_UPSTREAM`).
- No `SameSite=None`, no HttpOnly/Secure disable, no localStorage tokens.
- Private API responses marked `no-store` on the Next host.
- Tenant isolation / authz remain entirely on FastAPI.

---

## 8. Test matrix (actual local results)

| Area | Result | Notes |
| --- | --- | --- |
| Web Vitest | **71 passed** | Includes new `apiBase` + `apiProxyConfig` suites |
| UI tests | **24 passed** | Unchanged |
| TypeScript (`tsc --noEmit`) | **PASS** | |
| `next build` (staging upstream) | **PASS** | Rewrite present in routes manifest |
| Rewrite allowlist / open-proxy reject | **PASS** | Unit |
| Cookie hardening asserts (Lax/HttpOnly/Secure/no Domain) | **PASS** | Unit |
| Query / method / body / status via rewrite | **Config-level** | Platform rewrite; proven at build destination template |
| Live Preview Set-Cookie multi-header | **BLOCKED** | No deploy this phase |
| Browser login→/me session | **BLOCKED** | Requires Preview redeploy + env |
| Cross-tenant via Preview proxy | **BLOCKED** | Same |
| File upload / signed download through proxy | **N/A / BLOCKED** | No active browser multipart upload path; no deploy |
| Large body / redirect edge cases | **BLOCKED** | Needs Preview soak |
| Forged `X-Forwarded-*` auth bypass | **PASS (code review)** | Auth path ignores those headers |

---

## 9. Limitations

1. **Not deployed** — browser authentication remains unproven on Vercel until a Preview deploy with correct env.
2. Ephemeral Preview hostnames still need exact CORS entries on Render if anything calls Render directly.
3. Vercel request size/timeout limits apply to proxied bodies.
4. No WebSocket/SSE in current product; rewrite is insufficient if those appear later.
5. Local `.env` may still set absolute `NEXT_PUBLIC_API_URL` (cross-origin local mode); same-origin local mode = clear that var and rely on rewrite.

---

## 10. Deployment instructions (manual — do not auto-run)

**Order**

1. Ensure changes are on `release/p3-7b-staging` (commit when operator requests — not done here).
2. Vercel Preview env (`release/p3-7b-staging` only):
   - `API_REWRITE_UPSTREAM=https://micronest-medicalos.onrender.com` (**server-only**, not `NEXT_PUBLIC_`)
   - **Remove or empty** `NEXT_PUBLIC_API_URL` so the browser uses relative `/api/...`
   - Keep `COOKIE_SECURE=true`
3. Trigger staging Deploy Hook (Preview only — never `main`).
4. Capture new Preview URL if hostname changes; update Render `ALLOWED_ORIGINS` exact origin; keep existing Render origin until verification.
5. Run P3.7D browser matrix (login cookie stored on Preview host, `/me` 200, logout clears, tenant isolation).
6. Only after browser PASS: consider narrowing CORS (optional); do **not** remove CORS early.

**Render CORS:** keep current Preview origin + API self-origin until proof. Same-origin browser traffic does not require CORS for the proxied path, but direct API tools still may.

---

## 11. Rollback plan

1. Revert `next.config.mjs` rewrites / related web files; redeploy Preview.
2. Restore `NEXT_PUBLIC_API_URL=https://micronest-medicalos.onrender.com` if falling back to direct API (known cross-site cookie limitation).
3. Leave FastAPI cookie policy unchanged (no API rollback required for auth model).
4. Render CORS can remain as-is.

---

## 12. Verdict

**PASS** (updated after P3.7D.3)

| Gate | Status |
| --- | --- |
| Approved architecture implemented | Yes (Option A rewrite) |
| Cookie attributes not weakened | Yes (live Preview Set-Cookie: Lax/HttpOnly/Secure) |
| Open proxy prevented | Yes |
| Local tests / typecheck / build | Pass |
| Preview browser auth proof | **Pass** (17/17) — P3.7D.3 |
| Production / `main` | Untouched |

---

## Terminal summary

```
P3.7D.2 + P3.7D.3 — PASS
Same-origin rewrite verified on Preview dpl_G62cQNjWWFzRdwmxSW5MJDm8fJZG
Browser login/session/logout + tenant/role isolation PASS
Reports:
  docs/security/P3-7D2-same-origin-proxy-implementation.md
  docs/deployment/P3-7D3-same-origin-preview-verification.md
```
