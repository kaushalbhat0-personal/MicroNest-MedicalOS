# P3.7D — Vercel Staging Frontend Deployment Report

**Verdict: CONDITIONAL PASS — Preview deployed and CORS exact-origin wired; browser session blocked by cross-site cookie design (SameSite=Lax).**

Date: 2026-11-25  
Release branch: `release/p3-7b-staging`  
Backend (unchanged app code): Render `https://micronest-medicalos.onrender.com` @ `293dc668e7117f20a4b88e7a3047aa8e501c99b6`  
Real patient data: **prohibited** (synthetic staging only)

---

## 1. Vercel project identity

| Field | Value |
| --- | --- |
| Team | `kaushal-bhats-projects` (`team_5sXYYqiUCdvjfuzfdRK11yiS`) |
| Project name | `micro-nest-medical-os` |
| Project ID | `prj_7TvXFLPGYq59spXXgEdjb0xkfr9c` |
| Dashboard | https://vercel.com/kaushal-bhats-projects/micro-nest-medical-os/deployments |

## 2. Repository and root directory

| Field | Value |
| --- | --- |
| GitHub | `kaushalbhat0-personal/MicroNest-MedicalOS` |
| Framework | Next.js (`framework=nextjs`) |
| Root Directory | `apps/web` |
| Package manager | npm workspaces (root `package.json` workspaces: `apps/web`, `packages/*`) |
| Lockfile | root `package-lock.json` (also `apps/web/package-lock.json` present historically; install from monorepo root) |

## 3. Framework and build configuration

| Field | Value |
| --- | --- |
| Web package | `@healthcare-os/web` |
| Build | `next build` (`npm run build -w @healthcare-os/web` / `npm run web:build`) |
| Typecheck | `tsc --noEmit` |
| Unit tests | Vitest — web + `@healthcare-os/ui` |
| Node (Vercel) | `26.x` |
| Custom build/install on Vercel | unset (platform defaults) |

### Local pre-deploy validation (executed before Deploy Hook)

| Check | Result |
| --- | --- |
| TypeScript (`apps/web`) | PASS |
| Next.js production build | PASS |
| Web Vitest | **46** passed |
| UI Vitest | **24** passed |
| Client bundle secret pattern scan (`JWT_SECRET`, DB URLs, S3, Render key, etc.) | **0** hits |
| Render URL in local `.next` chunks (pre-cloud env) | 0 (expected locally) |

## 4. Production branch verification

| Field | Value |
| --- | --- |
| Vercel `link.productionBranch` | `main` (**unchanged**) |
| This work | **No** Production deployment triggered |
| Prior Production deployment observed | `dpl_EyTRWMqCMaANU6FWu5Vxq68Rda3q` on `main` (pre-existing; not modified) |

## 5. Staging branch verification

| Field | Value |
| --- | --- |
| Staging branch | `release/p3-7b-staging` |
| Local HEAD | `293dc668e7117f20a4b88e7a3047aa8e501c99b6` |
| `origin/release/p3-7b-staging` | same SHA |
| Deploy Hook | name `healthcare-os-staging`, ref `release/p3-7b-staging` (URL **not** recorded) |
| Hook HTTP result | `201` with job payload |

## 6. Preview deployment ID and URL

| Field | Value |
| --- | --- |
| Deployment ID | `dpl_DJJML6A5UzYYPawZw7wFEdqBDGAW` |
| Target | **Preview** (`target=null` / not `production`) |
| Status | READY |
| Preview URL | https://micro-nest-medical-8eeq5wwe6-kaushal-bhats-projects.vercel.app |
| Branch alias | https://micro-nest-medical-os-git-release-e1c39b-kaushal-bhats-projects.vercel.app |
| Exact origin used for CORS | `https://micro-nest-medical-8eeq5wwe6-kaushal-bhats-projects.vercel.app` |

**Note:** Team SSO Deployment Protection (`ssoProtection.deploymentType=all_except_custom_domains`) gates anonymous Preview access. An automation protection bypass was generated for smoke tooling only (secret not recorded in this report).

## 7. Deployed commit SHA

`293dc668e7117f20a4b88e7a3047aa8e501c99b6` — matches release branch and Render backend SHA.

## 8. Preview environment variable names and scopes only

Configured on Vercel **Preview** only, git branch `release/p3-7b-staging`:

| Key | Target | Branch scope | Notes |
| --- | --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | preview | `release/p3-7b-staging` | Backend base URL (public by design) |
| `COOKIE_SECURE` | preview | `release/p3-7b-staging` | Enables HSTS gate in `next.config` when true |

**Not set on Preview (correct):** database URLs, JWT secrets, Supabase service-role keys, S3 credentials, Render API keys, or other backend secrets.

**Source variable name (from `apps/web/lib/api.ts`):** `NEXT_PUBLIC_API_URL` only for API base. Auth uses HttpOnly cookies via `credentials: "include"` — no browser-side JWT storage.

Production env scope was **not** modified.

## 9. CORS exact-origin configuration status

| Item | Status |
| --- | --- |
| Backend parser | `ALLOWED_ORIGINS: list[str]` + Starlette `CORSMiddleware` (`allow_credentials=True`, explicit origins, never `*`) |
| Before | `["https://micronest-medicalos.onrender.com"]` |
| After | `["https://micronest-medicalos.onrender.com", "https://micro-nest-medical-8eeq5wwe6-kaushal-bhats-projects.vercel.app"]` |
| Wildcard | **not** used |
| Render autoDeploy | remains `no` |
| Preflight (OPTIONS `/api/v1/auth/login`) | `200`, `Access-Control-Allow-Origin` = exact Preview origin, `Allow-Credentials: true` |
| Browser CORS after fix (no stray bypass headers on API) | PASS — login POST reachable (401 for bad creds is expected) |

Render redeploy triggered solely for CORS env change: `dep-dc3ald0m7kps73dna4o0` → **live** @ `293dc668e711`.

Health after redeploy: `/api/healthz` 200, `/api/readyz` 200.

## 10. Render deployment ID / SHA if changed

| Field | Value |
| --- | --- |
| Service | `MicroNest-MedicalOS` (`srv-dc2tmb49v7es73dkqc9g`) |
| Branch | `release/p3-7b-staging` |
| Redeploy ID | `dep-dc3ald0m7kps73dna4o0` |
| Commit | `293dc668e711…` (same release SHA) |
| Reason | `ALLOWED_ORIGINS` exact Preview origin append only |
| Application code | **unchanged** |

## 11. Browser test matrix (actually executed)

Against Preview URL + Render API, synthetic accounts from `.env.p37c.staging` (values not printed).

| ID | Test | Outcome | Evidence (redacted) |
| --- | --- | --- | --- |
| A | Frontend HTTPS load | **PASS** | 200, host = Preview hostname (SSO bypass for automation) |
| B | Login page renders | **PASS** | Email / Password / Sign in visible |
| C | Synthetic owner login (browser session) | **FAIL** | login HTTP 200; `/me` → 401; cookies stored for API host = 0 |
| D | Invalid login fails safely | **PASS** | HTTP 401 + “Invalid email or password” + stays on `/login` |
| E | Logout | **BLOCKED** | Depends on authenticated browser session |
| F | Protected route (anon) | **PASS** | `/patients` → `/login` |
| G | Workspace dashboard | **BLOCKED** | Cross-site session |
| H | Patient directory | **BLOCKED** | Cross-site session |
| I | Appointment calendar | **BLOCKED** | Cross-site session |
| J | Reception queue | **BLOCKED** | Cross-site session |
| K | Patient 360 | **BLOCKED** | Cross-site session |
| L | Billing display | **BLOCKED** | Cross-site session |
| M | Portal login / own-record UI | **BLOCKED** | Cross-site session |
| N | Cross-tenant denial | **PASS (API same-site)** | Owner A → tenant B patient: **403**; wrong-tenant path: **404** |
| O | Receptionist owner-only controls | **PASS (API same-site)** | Receptionist `/staff` → **403**; no `staff.manage` in identity blob |
| P | CORS preflight + API calls | **PASS** | ACAO = Preview origin; credentialed login fetch completes |
| Q | Cookie / session security | **FAIL (expected design gap)** | See §12 |
| R | No secrets in page | **PASS** | No JWT/DB/S3/Render key patterns in HTML |
| S | Console errors | **FAIL (secondary)** | Expected 401s from unauthenticated `/me` after cookie drop |
| T | Mobile login layout | **PASS** | Email field visible at 390×844 |

Portal API login (same-site cookie jar, not browser UI): **PASS** (HTTP 200).

## 12. Authentication / cookie findings

**Root cause (security-preserving; not worked around):**

1. Preview origin: `*.vercel.app`
2. API origin: `micronest-medicalos.onrender.com`
3. Auth cookies `hos_access` / `hos_refresh` are set with `HttpOnly; Secure; SameSite=Lax; Path=/api…`
4. Observed on browser login response: **2× Set-Cookie** with those attributes
5. Chromium **did not store** any cookies for the API host (`stored_for_api=[]`)
6. Subsequent `fetch(..., credentials:"include")` to `/api/v1/auth/me` → **401**

Same-site API clients (urllib / Playwright `request` to Render host) **do** receive and send `hos_access` / `hos_refresh` successfully.

This is a **cross-site cookie architecture** issue for split Vercel↔Render hosting under `SameSite=Lax`. Fixing it requires a deliberate auth design change (e.g. same-site reverse proxy, BFF cookie on the Vercel origin, or `SameSite=None` + Secure with CSRF hardening). **No insecure workaround was applied** in this phase.

## 13. Tenant isolation findings

From same-site API probes with synthetic Owner A / Owner B:

- Tenant A patient list: 200 (2 patients)
- Tenant B patient list: 200 (1 patient)
- Owner A reading Owner B patient under B tenant scope: **403**
- Owner A reading B patient id under A tenant scope: **404**

Consistent with prior P3.7C synthetic isolation (59/59) — staging isolation still holds at API layer.

## 14. Portal findings

- Portal synthetic login over same-site API: **200**
- Portal browser UI journey: **BLOCKED** by the same cross-site cookie barrier
- No portal privilege expansion observed in API identity probe

## 15. Security findings

| Finding | Severity | Notes |
| --- | --- | --- |
| Cross-site session cookies not usable Preview→API | High (functional) / Correct (security posture) | Documented; no weakening |
| Vercel SSO on Preview | Info | Requires automation bypass or authenticated Vercel user |
| Preview env only public API URL + COOKIE_SECURE | OK | No backend secrets on Vercel |
| CORS exact origin | OK | No `*` |
| Deploy Hook URL | OK | Never printed, committed, or logged |
| Production branch / Production deploy | OK | Untouched |
| Real PHI | OK | Synthetic credentials only; no WhatsApp/email/payment side effects |

## 16. Skipped tests and blockers

| Item | Reason |
| --- | --- |
| G–M authenticated UI journeys | Blocker: cross-site `SameSite=Lax` cookies not stored/sent |
| E logout UI | Same |
| Full Playwright e2e suite against Preview | Same session blocker; matrix above used instead |
| Production CORS / Production env | Explicitly out of scope |
| Branch-alias CORS entry | Not required for this deployment URL; optional follow-up if alias becomes the stable staging entry |

## 17. Synthetic-data staging readiness

| Layer | Ready? |
| --- | --- |
| Render API staging | **Yes** (health/ready; hos_app; revision 0027; prior P3.7C/C.1 gates) |
| Vercel Preview frontend build | **Yes** (READY @ expected SHA; API URL env scoped) |
| Exact-origin CORS | **Yes** for this Preview deployment URL |
| End-to-end browser login → workspace | **No** — blocked by cross-site cookie design |
| Overall P3.7D | **CONDITIONAL PASS** |

## 18. Real patient data prohibition

Confirmed: exercises used `.env.p37c.staging` synthetic accounts only. No real patient data, no WhatsApp, no email, no live payment-provider charges.

---

## Terminal summary

```
Vercel Preview: READY  dpl_DJJML6A5UzYYPawZw7wFEdqBDGAW
SHA: 293dc668e7117f20a4b88e7a3047aa8e501c99b6  branch=release/p3-7b-staging  target=Preview
URL: https://micro-nest-medical-8eeq5wwe6-kaushal-bhats-projects.vercel.app
Production branch: main (unchanged)  |  main not deployed
Preview env: NEXT_PUBLIC_API_URL, COOKIE_SECURE (branch-scoped)
Render CORS: exact Preview origin added; redeploy dep-dc3ald0m7kps73dna4o0 live
Browser: A/B/D/F/P/R/T PASS; C/Q FAIL (SameSite=Lax cross-site); G–M BLOCKED
API same-site: cross-tenant 403/404 PASS; receptionist staff 403 PASS
Evidence: docs/deployment/P3-7D-vercel-staging-deployment-report.md
```
