# P3.7D.1 — Same-Origin Auth Architecture Audit

**Verdict: READY FOR IMPLEMENTATION** (staging Preview via Vercel same-origin rewrite; production path = shared registrable domain later)

Date: 2026-11-25  
Scope: Architecture / security plan only — **no code changes, no commits, no deployments**  
Current Preview: `https://micro-nest-medical-8eeq5wwe6-kaushal-bhats-projects.vercel.app`  
API: `https://micronest-medicalos.onrender.com`  
Branch / SHA: `release/p3-7b-staging` @ `293dc668e7117f20a4b88e7a3047aa8e501c99b6`

---

## 1. Root cause

Browser authentication fails because the **frontend and API are different sites**, while auth cookies are issued as:

| Attribute | Value |
| --- | --- |
| Names | `hos_access`, `hos_refresh` |
| HttpOnly | `true` |
| Secure | `true` (Render `COOKIE_SECURE=true`) |
| SameSite | **`Lax`** (hardcoded) |
| Domain | **unset** (`COOKIE_DOMAIN=null` → host-only for the **API host**) |
| Path | `hos_access` → `/api`; `hos_refresh` → `/api/v1/auth` |
| Max-Age | access ≈ 10 minutes; refresh ≈ `REFRESH_TOKEN_DAYS` (30) |

### Why the browser rejects usable session cookies

1. Login `fetch` runs from origin `https://…vercel.app` to `https://micronest-medicalos.onrender.com` (**cross-site**).
2. FastAPI responds `200` + `Set-Cookie` with `SameSite=Lax; Secure; HttpOnly` (observed in P3.7D).
3. Modern Chromium **does not retain** these as a usable third-party / cross-site session for subsequent credentialed XHR/fetch (`stored_for_api=[]` in P3.7D).
4. Later `fetch(..., credentials: "include")` to `/api/v1/auth/me` sends **no** `hos_access` → **401**.
5. Same-site clients talking **only** to Render (urllib / Playwright APIRequest) store and send cookies correctly — proving the API auth path works; the failure is **browser cross-site cookie policy**, not credential validation.

`SameSite=None` is **not** recommended here (would require CSRF tokens the app does not have). HttpOnly/Secure must stay.

---

## 2. End-to-end authentication trace (as implemented)

### 2.1 Components inspected

| Area | Location | Finding |
| --- | --- | --- |
| API client | `apps/web/lib/api.ts` | `NEXT_PUBLIC_API_URL` + path; `credentials: "include"`; optional `X-Tenant` |
| Login UI | `apps/web/app/login/page.tsx` | `api.post("/api/v1/auth/login")` then workspace routing from body / `/me` |
| Logout UI | `apps/web/app/shell.tsx`, `portal/shell.tsx` | `api.post("/api/v1/auth/logout")` then clear tenant + `/login` |
| Next middleware | — | **None** (no `middleware.ts`) |
| Next `/app/api` | — | **None** (no App Router API routes; `/api/*` free for proxy) |
| `next.config.mjs` | headers only | **No rewrites** today |
| Login / refresh | `backend/app/api/v1/auth.py` | Issues session + cookies |
| Logout / me / sessions | `backend/app/api/v1/account.py` | Cookie clear on logout; `/me` via `get_current_user` |
| Cookie helpers | `backend/app/platform/security/cookies.py` | Lax / HttpOnly / paths as above |
| Session issue | `backend/app/api/v1/_shared.py` `issue_session_pair` / `set_session_cookies` | JWT access + `sessionId.secret` refresh |
| Auth dependency | `backend/app/api/deps.py` | Cookie **or** Bearer; session DB checks; tenant via `X-Tenant` |
| CORS | `backend/app/main.py` | Explicit `ALLOWED_ORIGINS`, credentials allowed, no `*` |
| CSRF tokens | — | **Not implemented** — CSRF defense is **`SameSite=Lax` + CORS allowlist** |
| WebSocket / SSE | — | **Not used** in current backend/web |
| Uploads | web | No multipart browser upload path in active UI (object refs only) |
| Protected routes | client-side redirects to `/login` | Authorization remains **API-enforced** |

### 2.2 Login sequence (current Preview)

```
1. Browser POST https://onrender…/api/v1/auth/login
   Origin: https://…vercel.app
   Body: { email, password }
   credentials: include

2. FastAPI rate-limits (IP + account), authenticates, create_session()

3. Response 200 JSON MeResponse
   + Set-Cookie: hos_access=…; Path=/api; HttpOnly; Secure; SameSite=Lax
   + Set-Cookie: hos_refresh=…; Path=/api/v1/auth; HttpOnly; Secure; SameSite=Lax
   Domain attribute omitted → host-only for onrender.com

4. Browser: cookie not retained for subsequent cross-site API calls (P3.7D evidence)

5. Browser GET/POST https://onrender…/api/v1/… with credentials:include
   → no hos_access → 401

6. FastAPI get_current_user never sees cookie; tenant context never established
```

### 2.3 Intended sequence after same-origin proxy

```
1. Browser POST https://…vercel.app/api/v1/auth/login   (same-site)
2. Vercel rewrite/proxy → https://onrender…/api/v1/auth/login
3. FastAPI validates + Set-Cookie (Domain unset)
4. Browser stores cookies for …vercel.app (host-only), Path=/api…
5. Browser GET https://…vercel.app/api/v1/auth/me (sends hos_access)
6. Proxy → Render; FastAPI validates JWT + session + (later) X-Tenant
```

### 2.4 CSRF reality check

- There is **no** CSRF header/token middleware today.
- Safety model assumes **first-party cookies with `SameSite=Lax`**.
- A same-origin proxy **preserves** that model (browser ↔ Vercel is first-party).
- Moving to `SameSite=None` without adding CSRF would be a **security regression** — forbidden by this plan.
- CORS allowlist remains relevant for any **direct** browser→Render calls; same-origin proxied calls are not cross-origin from the browser’s perspective.

---

## 3. Same-origin proxy evaluation (Option A)

### 3.1 Path compatibility

All browser API calls use paths under `/api/...` (`/api/v1/...`, plus health `/api/healthz` / `/api/readyz` if probed).

Proposed rewrite (path-preserving):

```text
source:      /api/:path*
destination: https://micronest-medicalos.onrender.com/api/:path*
```

Examples:

| Browser URL | Upstream |
| --- | --- |
| `/api/v1/auth/login` | `https://micronest-medicalos.onrender.com/api/v1/auth/login` |
| `/api/v1/auth/me` | `…/api/v1/auth/me` |
| `/api/healthz` | `…/api/healthz` |

No Next.js App Router `/api` conflict today.

### 3.2 Cookie / header behavior

| Concern | Assessment |
| --- | --- |
| Set-Cookie forwarding | Vercel external rewrites act as reverse proxy; Set-Cookie should reach browser. **Must be proven** in Preview before declaring auth fixed. Fallback: thin Route Handler proxy if headers drop. |
| Host-only cookies | Keep `COOKIE_DOMAIN` **unset**. Cookies bind to Preview hostname. |
| Secure / HttpOnly / SameSite | Preserve as set by FastAPI; do not rewrite cookie attributes in the proxy. |
| SameSite=Lax | Becomes effective: request is same-site to Vercel. |
| Path `/api` | Matches proxied paths — correct. |
| Authorization Bearer | Still works if ever used; browser path remains cookies. |
| CSRF | Unchanged (Lax); proxy must not invent CSRF bypass. |
| Origin | Browser Origin = Preview. Upstream may see forwarded Origin; keep Preview in `ALLOWED_ORIGINS`. Do **not** trust client `X-Forwarded-*` for auth decisions. |
| Host | Upstream Host will be Render’s; auth does not key off Host today. |
| Body / status / redirects | JSON APIs; avoid caching; do not auto-follow mutating redirects at edge. |
| Uploads / downloads | No active browser multipart today; if added later, verify body size + timeout under Vercel limits. |
| WebSocket / SSE | Not used; rewrite proxy is insufficient if added later → dedicated plan. |
| Caching | **Must** force `Cache-Control: private, no-store` on `/api/*` responses (Vercel CDN must not cache authenticated JSON). |
| Timeouts / size | Vercel serverless/edge limits apply; acceptable for current JSON API surface; monitor large billing/export payloads. |
| Rate-limit IP | `request.client.host` on Render may see Vercel egress; auth still cookie/session based. Do not start trusting forged `X-Forwarded-For` from the browser. |

### 3.3 Trust boundary

```
Browser  --same-origin-->  Vercel edge (rewrite)  --server-side-->  Render FastAPI
```

- Browser cannot spoof “being Vercel” to skip cookies; it still needs valid `hos_*` cookies for the Preview host.
- Authn/authz remain on FastAPI (JWT + DB session + RLS + permissions).
- Optional hardening (later): restrict Render ingress to Vercel / known CIDRs — **not** required to fix cookies; do not fake trust via client headers.

---

## 4. Architecture comparison

| | **A. Vercel rewrite → Render** | **B. Shared registrable domain** (`app.` + `api.` or reverse-proxy) | **C. Next.js BFF / Route Handlers** |
| --- | --- | --- | --- |
| **Idea** | Browser calls `/api/*` on Preview; edge proxies to Render | `app.example.com` + `api.example.com` with Domain cookie or single origin | Next server forwards `/api/*` or re-issues session |
| **Fixes Lax cookies?** | Yes (same site as UI) | Yes (same-site or Domain=parent) | Yes if browser only talks to Next |
| **Security** | Keeps FastAPI as auth authority; preserves HttpOnly/Lax/Secure | Strongest long-term control of cookie Domain + TLS | Thin proxy OK; “re-mint cookies in Next” increases secret surface — **avoid** |
| **CSRF** | Still Lax-based (OK) | Lax-based if same-site | Same if proxy-only |
| **Complexity** | Low–medium (config + one client env change) | Medium–high (DNS, certs, Render custom domain) | Medium (code + streaming edge cases) |
| **Cost** | Low (existing Vercel/Render) | Domain + ops | Eng time |
| **Maintainability** | Good for staging; Preview URL changes need CORS/origin updates | Best for production | Extra code path to keep in sync |
| **Compatibility with current FastAPI auth** | **High** — path/cookie design already `/api` | High | High if transparent proxy; low if reimplementing sessions |
| **Risks** | Must verify Set-Cookie passthrough; CDN caching; Preview hostname churn | Domain procurement / setup time | Duplicate bugs; accidental secret exposure if misbuilt |

### Recommendation (evidence-based)

**Implement Option A for P3.7D.1 staging**, with:

1. Path-preserving `/api/:path*` rewrite to Render.
2. Browser client using **same-origin relative** API base (empty / unset cloud `NEXT_PUBLIC_API_URL` meaning “same origin”).
3. Keep `COOKIE_DOMAIN` null; keep `SameSite=Lax`, HttpOnly, Secure.
4. Keep Preview origin in Render `ALLOWED_ORIGINS` for defense-in-depth / any direct calls.
5. Explicit **no-store** on `/api/*`.
6. **Fallback** to Option C *thin* Route Handler proxy only if Preview proves Set-Cookie is stripped by rewrites.
7. **Production track**: Option B (custom domain) so cookie/CORS hosts are stable and not tied to ephemeral `*.vercel.app` deployment URLs.

**Not recommended as default:** `SameSite=None`, localStorage tokens, disabling HttpOnly/Secure, or trusting arbitrary `X-Forwarded-*` for authentication.

---

## 5. Implementation plan (no code in this phase)

### 5.1 Files likely to change (future PR)

| File | Change |
| --- | --- |
| `apps/web/next.config.mjs` | Add `rewrites()` to Render; add `/api/:path*` `Cache-Control: private, no-store` headers |
| `apps/web/lib/api.ts` | Allow empty/`""` API base for same-origin (keep localhost default for local without rewrite) |
| Vercel Preview env | Set `NEXT_PUBLIC_API_URL` to empty string **or** omit and teach client “cloud = relative”; keep `COOKIE_SECURE=true` |
| Render `ALLOWED_ORIGINS` | Keep exact Preview origin(s); add branch alias if used as primary entry |
| Docs | Update P3.7D deployment notes + this audit’s implementation checklist |
| Optional fallback | `apps/web/app/api/[...path]/route.ts` transparent proxy — only if rewrite fails cookie test |
| **Do not change** | `cookies.py` SameSite/HttpOnly/Secure; JWT secret handling; CSRF weakening; production `main` |

### 5.2 Exact routing

```js
// conceptual — not applied in this audit
async rewrites() {
  const upstream = process.env.API_REWRITE_UPSTREAM
    || "https://micronest-medicalos.onrender.com";
  return [
    { source: "/api/:path*", destination: `${upstream}/api/:path*` },
  ];
}
```

Local dev: either run rewrite to `http://127.0.0.1:8000` or keep absolute `NEXT_PUBLIC_API_URL=http://localhost:8000` (today’s default).

### 5.3 Vercel configuration

- Preview env (branch `release/p3-7b-staging`):
  - `API_REWRITE_UPSTREAM=https://micronest-medicalos.onrender.com` (server-only; **not** `NEXT_PUBLIC_`)
  - `NEXT_PUBLIC_API_URL=` (empty → relative `/api/...`) **or** documented equivalent
  - `COOKIE_SECURE=true`
- Do not put JWT, DB, S3, or Render API keys on Vercel.
- Redeploy Preview after config (new deployment may change hostname → update CORS).
- Prefer also attaching CORS for **branch alias** if that becomes the stable staging URL.

### 5.4 Render environment

- `COOKIE_SECURE=true` (unchanged)
- `COOKIE_DOMAIN` unset (unchanged — critical)
- `ALLOWED_ORIGINS` includes exact Preview origin(s) (already done for current deployment URL)
- `autoDeploy=no` (unchanged)
- No Production CORS changes

### 5.5 Cookie / CSRF / CORS policy (target)

| Policy | Rule |
| --- | --- |
| Cookie | HttpOnly + Secure + SameSite=Lax; Domain unset; paths unchanged |
| CSRF | Continue to rely on Lax for first-party; **do not** switch to None without a CSRF token design |
| CORS | Exact origins only; credentials allowed; no `*` |
| Authz | Unchanged FastAPI session + permissions + RLS |
| Secrets | Remain on Render only |

### 5.6 Deployment sequence

1. Land rewrite + client base URL change on `release/p3-7b-staging` (or staging PR).
2. Update Vercel Preview env (relative API + upstream).
3. Trigger Preview deploy (hook); capture **new** Preview URL if hostname changes.
4. Update Render `ALLOWED_ORIGINS` to new exact origin if needed; controlled redeploy.
5. Run §6 browser matrix; **only then** claim auth fixed.
6. Do not touch `main` / Production.

### 5.7 Rollback

1. Revert `next.config.mjs` rewrites / client API base change; redeploy Preview.
2. Restore previous Preview `NEXT_PUBLIC_API_URL` absolute Render URL if needed.
3. Render CORS can remain (harmless) or revert to prior list.
4. Auth model unchanged on API — rollback is frontend/edge only.

---

## 6. Security test plan (synthetic accounts only)

Accounts: `.env.p37c.staging` (never print secrets). Target: Preview origin after proxy.

| # | Test | Pass criteria |
| --- | --- | --- |
| 1 | Login cookie stored | After UI login, `document` cannot read cookie (HttpOnly) but Playwright `context.cookies(previewOrigin)` shows `hos_access` / `hos_refresh` |
| 2 | Cookie attributes | `Secure`, `HttpOnly`, `SameSite=Lax` (or `Lax`); Path `/api` and `/api/v1/auth`; Domain empty or Preview host |
| 3 | Authenticated same-origin calls | `/api/v1/auth/me` → 200 via Preview; dashboard loads |
| 4 | Logout clears cookie | After logout, cookies absent/expired; `/me` → 401 |
| 5 | Expired session rejected | Revoke/expire session server-side → `/me` 401 |
| 6 | Invalid session rejected | Tamper cookie value → 401 |
| 7 | CSRF missing/invalid | N/A until CSRF tokens exist; **guardrail**: assert SameSite remains Lax (not None) |
| 8 | Foreign Origin rejected | Direct browser call from evil origin to Render without allowlist → CORS fail; proxied app must not accept cross-site credential use from foreign sites |
| 9 | Tenant isolation | Owner A cannot read Owner B patient (403/404) through Preview proxy |
| 10 | Receptionist limits | Receptionist cannot perform owner-only staff manage (403) |
| 11 | Portal vs staff | Portal user cannot open staff routes/APIs |
| 12 | Upload/download auth | If exercised, signed/object access still requires auth; no anonymous proxy bypass |
| 13 | No private caching | `/api/v1/auth/me` response headers include no shared CDN cache; repeat with cookie variation |
| 14 | Forged forwarding headers | Client-supplied `X-Forwarded-For` / `X-Real-IP` must not grant auth or elevate identity; session still cookie-bound |

**Claim rule:** Browser authentication is fixed only after tests **1–4** and **9–11** pass against the live Preview URL.

---

## 7. Security risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Rewrite drops `Set-Cookie` | Prove with Playwright; fallback thin Route Handler proxy |
| CDN caches private API | Force `private, no-store` on `/api/*` |
| Preview URL churn breaks CORS | Update exact origins; prefer branch alias + Option B later |
| SSRF / open proxy | Rewrite destination fixed to Render staging URL from server env only |
| Secret leakage to Vercel | No JWT/DB/S3 on Vercel; only public/routing config |
| Assuming CSRF tokens exist | Document gap; keep Lax; add CSRF design before any None |
| Trusting `X-Forwarded-*` | Auth ignores them; rate-limit IP coarseness accepted |
| Direct Render still reachable | Accept for staging API tests; optional IP allowlist later |

---

## 8. Verdict

**READY FOR IMPLEMENTATION**

- Root cause is confirmed: cross-site `SameSite=Lax` cookies between Vercel Preview and Render.
- Option **A** (same-origin Vercel rewrite to Render) matches existing cookie paths and FastAPI auth without weakening controls.
- Option **B** remains the preferred production end-state.
- Option **C** is a fallback proxy implementation, not a session re-architecture.
- No code, deploy, or production changes were made in this audit phase.
- Browser auth must not be declared fixed until the §6 matrix passes on Preview.

---

## 9. Terminal summary

```
P3.7D.1 AUDIT — READY FOR IMPLEMENTATION
Root cause: cross-site hos_* cookies (SameSite=Lax) Vercel→Render
Recommend: Option A same-origin /api rewrite → Render; keep Lax/HttpOnly/Secure
Fallback: thin Next Route Handler proxy if Set-Cookie dropped
Production track: Option B shared registrable domain
CSRF: no token layer today — Lax is the control; do not use SameSite=None
Report: docs/security/P3-7D1-same-origin-auth-architecture-audit.md
No code/deploy/commit in this phase
```
