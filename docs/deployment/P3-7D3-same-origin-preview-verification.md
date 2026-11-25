# P3.7D.3 — Same-Origin Preview Deployment & Browser Verification

**Verdict: PASS**

Date: 2026-11-25  
Implementation: `docs/security/P3-7D2-same-origin-proxy-implementation.md`  
Production branch `main`: **unchanged**  
Commits / pushes: **none**

---

## 1. Git branch and diff summary

| Item | Value |
| --- | --- |
| Branch | `release/p3-7b-staging` |
| Baseline HEAD | `293dc668e7117f20a4b88e7a3047aa8e501c99b6` (unchanged on remote) |
| P3.7D.2 code | **Uncommitted** local working tree |

### In-scope for Preview deploy (apps/web)

- `apps/web/next.config.mjs` — allowlisted `/api` rewrite + no-store
- `apps/web/lib/api.ts`, `apiBase.ts`, `apiProxyConfig.mjs` (+ tests)
- `.env.example` docs for `API_REWRITE_UPSTREAM`

### Unrelated local changes (preserved, not required for auth fix)

- Prior P3.7A–D scripts/docs, `.gitignore`, P3-7B deployment docs, UI research, etc.

### Security review of ship set

- No Deploy Hook URL / secrets in tracked files
- Upstream allowlist closed (`apiProxyConfig.mjs`)
- Browser client relative `/api` by default
- Cookie attributes unchanged (Lax / HttpOnly / Secure / host-only)
- No Production config in this ship set

### Deploy method note

The staging **Deploy Hook cannot deploy uncommitted files**. Per objective (“deploy the uncommitted P3.7D.2 implementation” + “no commit/push”), Preview was created with:

`npx vercel deploy --yes --archive=tgz` (root monorepo, **not** `--prod`).

---

## 2. Vercel Preview environment (names/scopes only)

| Key | Scope | Notes |
| --- | --- | --- |
| `API_REWRITE_UPSTREAM` | Preview (all) | Server-only; not `NEXT_PUBLIC_` |
| `API_REWRITE_UPSTREAM` | Preview (`release/p3-7b-staging`) | Same value, branch-scoped |
| `COOKIE_SECURE` | Preview (`release/p3-7b-staging`) | Pre-existing |
| `NEXT_PUBLIC_API_URL` | — | **Removed** from Preview (branch-scoped) |

Production-scoped variables: **not modified**.

Also: project `nodeVersion` set `26.x` → `24.x` so Preview builds succeed on current Vercel builders (project-wide runtime setting; production branch still `main`).

---

## 3. Preview deployment

| Field | Value |
| --- | --- |
| Deployment ID | `dpl_G62cQNjWWFzRdwmxSW5MJDm8fJZG` |
| Target | **Preview** (`target=null`) |
| Status | READY |
| Preview URL | https://micro-nest-medical-3jjkc67ds-kaushal-bhats-projects.vercel.app |
| Exact origin | `https://micro-nest-medical-3jjkc67ds-kaushal-bhats-projects.vercel.app` |
| Git SHA on deployment | local uncommitted tree (baseline parent `293dc668…`) |
| Production / `main` deploy | **Not** triggered |

---

## 4. Pre-deploy checks (actual)

| Check | Result |
| --- | --- |
| Web Vitest | **71** passed |
| UI tests | **24** passed |
| TypeScript | PASS |
| `next build` + rewrite | PASS → `/api/:path*` → `https://micronest-medicalos.onrender.com/api/:path*` |
| Client bundle secret patterns | **0** hits |
| Render URL in static JS chunks | **0** |

---

## 5. Rewrite verification (live Preview)

| Check | Result |
| --- | --- |
| `GET /api/healthz` via Preview | **200** `{"status":"ok"}` |
| Browser API host | Preview only (`apiViaRender=0`) |
| Redirect to Render hostname | **None** |
| `Cache-Control` on `/api/*` | `private, no-store, no-cache, must-revalidate` |

---

## 6. Cookie attributes observed (login Set-Cookie)

| Cookie | HttpOnly | Secure | SameSite | Path | Domain |
| --- | --- | --- | --- | --- | --- |
| `hos_access` | true | true | Lax | `/api` | unset (host-only) |
| `hos_refresh` | true | true | Lax | `/api/v1/auth` | unset (host-only) |

Jar after login: `hos_access` + `hos_refresh` present for Preview host.  
Functional proof: same-origin `GET /api/v1/auth/me` → **200**.

---

## 7. Browser test matrix (Playwright, synthetic `.env.p37c.staging`)

| ID | Result |
| --- | --- |
| A_healthz_proxy | **PASS** |
| A_login_page | **PASS** |
| A_no_render_redirect | **PASS** |
| B_login_cookies | **PASS** (login 200, me 200, 2× Set-Cookie) |
| B_cookie_attrs | **PASS** |
| B_cookie_paths | **PASS** |
| C_dashboard | **PASS** (`/`) |
| C_session_refresh | **PASS** (me 200) |
| C_logout | **PASS** (me 401, cookies cleared) |
| C_invalid_session | **PASS** (me 401) |
| D_cross_tenant | **PASS** (403) |
| D_receptionist_owner_controls | **PASS** (staff 403) |
| D_portal_staff_denied | **PASS** (portal path / staff API 403) |
| E_cache_control | **PASS** |
| E_no_secrets_in_page | **PASS** |
| E_forged_forwarded_headers | **PASS** (me 401) |
| E_console | **PASS** (only expected 401 resource noise) |

**Counts: 17 PASS / 0 FAIL / 0 BLOCKED**

---

## 8. CORS cleanup decision

All verified browser API traffic used the **Vercel same-origin proxy** (`apiViaRender=0`).

**No Render `ALLOWED_ORIGINS` changes in this phase.**

Proposal for a later, separate change (not executed): after a stable branch alias is adopted and no tooling depends on direct browser→Render calls, narrow CORS to non-browser clients / drop ephemeral Preview hostnames. Keep current allowlist until that evidence review is done.

---

## 9. Skipped / notes

| Item | Note |
| --- | --- |
| Deploy Hook | Not used — cannot ship uncommitted tree |
| Expired-session timer soak | Covered via invalid JWT cookie + logout; not a multi-minute clock wait |
| Upload/download | No active browser multipart path exercised |
| First healthz attempt | Timed out at 30s (cold); re-check + urllib @ 90s **PASS** |

---

## 10. Final verdict

**PASS** — same-origin `/api` proxy on Vercel Preview authenticates the browser with `SameSite=Lax` HttpOnly Secure cookies; tenant/role isolation holds; no Production/`main` deployment; Render CORS left intact.
