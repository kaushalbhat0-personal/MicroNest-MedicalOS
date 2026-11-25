# P3.7D.4 — Release Reconciliation (approval required)

**Status: READY FOR APPROVAL — no commit / push / deploy performed**

Date: 2026-11-25  
Verified Preview: https://micro-nest-medical-3jjkc67ds-kaushal-bhats-projects.vercel.app  
Deployment ID: `dpl_G62cQNjWWFzRdwmxSW5MJDm8fJZG` (CLI archive Preview; **not** a Git commit SHA)  
Intended branch: `release/p3-7b-staging`  
Backend: `https://micronest-medicalos.onrender.com` @ same release branch  
Production `main`: untouched

---

## 1. Current Git branch and SHA

| Item | Value |
| --- | --- |
| Current branch | `release/p3-7b-staging` |
| Local HEAD | `293dc668e7117f20a4b88e7a3047aa8e501c99b6` |
| `origin/release/p3-7b-staging` | `293dc668e7117f20a4b88e7a3047aa8e501c99b6` (in sync) |
| `origin/main` | `2a0974e41af9e334e147794f45e258f34d6814d3` |
| Staged changes | **none** |
| Working tree | Dirty — modified + many untracked files (all preserved) |

**Important:** Preview `dpl_G62cQNj…` was built from a **local CLI archive** of the working tree. It is **not** reproducible from Git HEAD alone until the proposed file set is committed and pushed.

---

## 2. Working tree summary

### Modified (tracked)

| Path | Relation to P3.7D.3 |
| --- | --- |
| `apps/web/next.config.mjs` | **Core** — rewrite + no-store |
| `apps/web/lib/api.ts` | **Core** — relative `apiUrl` |
| `.env.example` | **Docs** — `API_REWRITE_UPSTREAM` guidance (+ prior cloud placeholders) |
| `.gitignore` | Partial — adds `.vercel` / `.env*` (see caveat below) |
| `docs/deployment/P3-7B-*.md` | Unrelated to proxy — **exclude** from this release commit |

### Untracked — proposed for release

| Path | Role |
| --- | --- |
| `apps/web/lib/apiBase.ts` | Same-origin base URL helper |
| `apps/web/lib/apiBase.test.ts` | Unit tests |
| `apps/web/lib/apiProxyConfig.mjs` | Allowlist + rewrite/header helpers |
| `apps/web/lib/apiProxyConfig.test.ts` | Proxy/security unit tests |
| `.vercelignore` | Keeps CLI Preview uploads small |
| `docs/security/P3-7D1-same-origin-auth-architecture-audit.md` | Audit |
| `docs/security/P3-7D2-same-origin-proxy-implementation.md` | Implementation evidence |
| `docs/deployment/P3-7D3-same-origin-preview-verification.md` | Browser verification |
| `docs/deployment/P3-7D4-release-reconciliation.md` | This document |

### Untracked — must **not** enter Git

| Path | Reason |
| --- | --- |
| `.vercel/`, `apps/web/.vercel/` | Local link / OIDC / env pulls |
| `.env`, `.env.local`, `.env.p37c.staging` | Secrets / synthetic passwords |
| `scripts/_p37d3_verify_results.json`, `_p37d_smoke_results.json`, other `_p37*evidence*.json` | May contain sensitive markers / local ops data |
| `apps/web/playwright-report/`, `apps/web/test-results/` | Generated artifacts |
| `.playwright-mcp/` | Local MCP captures |
| `scripts/_p37*` deploy/smoke tooling | Ops helpers; not required for app reproducibility; risk of accidental secret leakage |
| `docs/ui-ux/**`, dental research, older P3.7B/C reports (optional later) | Out of verified proxy scope |
| `apps/web/.gitignore`, `apps/web/.vercelignore` | Dual-link artifacts from CLI; root ignore is enough |

---

## 3. Deployed Preview ID and URL

| Field | Value |
| --- | --- |
| ID | `dpl_G62cQNjWWFzRdwmxSW5MJDm8fJZG` |
| URL | https://micro-nest-medical-3jjkc67ds-kaushal-bhats-projects.vercel.app |
| Target | Preview |
| Method | `vercel deploy --archive=tgz` (uncommitted tree) |
| Browser matrix | **17/17 PASS** (P3.7D.3) |

Vercel Preview env (names only): `API_REWRITE_UPSTREAM` (Preview), `COOKIE_SECURE` (Preview branch); `NEXT_PUBLIC_API_URL` removed from Preview.

---

## 4. Exact verified implementation (checklist)

| Requirement | Local tree | Notes |
| --- | --- | --- |
| 1. Same-origin `/api` rewrite | **Yes** | `next.config.mjs` → `apiRewriteRules` |
| 2. Upstream allowlisted | **Yes** | Render staging + local only |
| 3. `API_REWRITE_UPSTREAM` server-only | **Yes** | Not `NEXT_PUBLIC_`; documented in `.env.example` |
| 4. Relative `/api` client | **Yes** | `resolveApiBase()` defaults to `""` |
| 5. Preview `NEXT_PUBLIC_API_URL` removal documented | **Yes** | P3.7D.3 + `.env.example` |
| 6. Cookies Secure / HttpOnly / SameSite=Lax | **Yes** | `cookies.py` unchanged; live Preview confirmed |
| 7. No auth/CSRF weakening | **Yes** | No `SameSite=None`; no CSRF token fake-add |
| 8. No arbitrary proxy destination | **Yes** | Allowlist throws on non-allowed origins |
| 9. No private response caching | **Yes** | `Cache-Control: private, no-store…` on `/api/*` |
| 10. No accidental Production config in repo | **Yes** | No Production branch / `main` edits |

---

## 5. Differences: deployed vs local vs intended branch

| Axis | Finding |
| --- | --- |
| Deployed Preview vs current local **apps/web proxy files** | **No material difference** — same rewrite/client/allowlist that was archive-deployed and browser-verified |
| Deployed Preview vs Git HEAD `293dc668` | **Missing entirely** — HEAD has no same-origin proxy |
| Intended branch `release/p3-7b-staging` | Points at `293dc668`; needs one commit of the proposed file set for Git reproducibility |
| CLI deployment ID vs Git SHA | **Not equivalent** — do not treat `dpl_G62cQNj…` as a commit |

Minor local-only ops files changed after Preview (verify scripts/results) — **not** part of the Next.js runtime ship set.

---

## 6. Proposed release file list

### Include (single focused commit recommended)

```
apps/web/next.config.mjs
apps/web/lib/api.ts
apps/web/lib/apiBase.ts
apps/web/lib/apiBase.test.ts
apps/web/lib/apiProxyConfig.mjs
apps/web/lib/apiProxyConfig.test.ts
.env.example
.vercelignore
.gitignore                    # ONLY if corrected (see blocker note)
docs/security/P3-7D1-same-origin-auth-architecture-audit.md
docs/security/P3-7D2-same-origin-proxy-implementation.md
docs/deployment/P3-7D3-same-origin-preview-verification.md
docs/deployment/P3-7D4-release-reconciliation.md
```

### Explicitly exclude

- All `scripts/_p37*` and evidence JSON
- Playwright/MCP artifacts
- `.vercel`, `.env*`, `.env.p37c.staging`
- Unrelated P3.7B doc edits (`docs/deployment/P3-7B-*.md`) unless a separate commit is approved
- `docs/ui-ux/**` and other unrelated untracked trees

### `.gitignore` caveat (blocker if committed as-is)

Current dirty `.gitignore` appends:

```gitignore
.vercel
.env*
```

Existing earlier lines already have `.env` / `.env.*` / `!.env.example`. A trailing `.env*` **overrides** the un-ignore of `.env.example` for ignore matching.

**Proposed fix before commit (awaiting approval to edit):**

```gitignore
.vercel
.env*
!.env.example
```

or simply add **only** `.vercel`.

---

## 7. Tests and results (this phase)

| Check | Result |
| --- | --- |
| Web Vitest | **71** passed |
| UI tests | **24** passed |
| TypeScript | PASS |
| `next build` with staging upstream | PASS |
| Rewrite in routes manifest | `/api/:path*` → `https://micronest-medicalos.onrender.com/api/:path*` |
| P3.7D.3 browser matrix | **17/17 PASS** (prior phase; still the verification of this tree) |

---

## 8. Secret scanning results

| Target | Result |
| --- | --- |
| Core proxy source/tests | **clean** |
| Evidence docs P3.7D1–D3 | **clean** |
| `cookies.py` | **clean** (still `samesite="lax"`, `httponly=True`) |
| `.env.example` | Marker `sbp_` in a **comment** about Supabase PATs (placeholder docs only — no real token) |
| Local evidence JSON / `.env.p37c.staging` / `.vercel` | Present locally — **excluded** from proposed commit |

No Deploy Hook URLs found in proposed release files.

---

## 9. Blockers

| Blocker | Severity | Resolution (needs approval) |
| --- | --- | --- |
| Uncommitted implementation ≠ Git HEAD | **Release** | Commit proposed file set to `release/p3-7b-staging` |
| Deploy Hook cannot redeploy until push | Ops | After push, optional Hook Preview to prove Git-based reproducibility |
| Dirty `.gitignore` `.env*` order | Medium | Fix negation before including `.gitignore` |
| Many unrelated dirty/untracked files | Process | Keep out of this commit; preserve on disk |

No security-critical code blockers for the proxy itself.

---

## 10. Proposed commit message

```
feat(web): add same-origin /api rewrite for staging Preview auth

Proxy browser /api to allowlisted Render upstream so SameSite=Lax
HttpOnly cookies work on Vercel Preview without SameSite=None.
```

---

## 11. Proposed push target

| Item | Value |
| --- | --- |
| Remote branch | `origin/release/p3-7b-staging` |
| Force push | **No** |
| Merge to `main` | **No** (not in this approval) |
| Production deploy | **No** |
| After push | Optional: trigger staging Deploy Hook → new Preview; re-spot-check login (recommended for Git↔Preview parity) |

---

## 12. Approval gate

Awaiting **explicit** approval to:

1. (Optional) Fix `.gitignore` negation order.
2. Stage **only** the proposed release file list.
3. Create **one** commit with the message above.
4. Push to `origin/release/p3-7b-staging` (non-force).

Until then: **no commit, no push, no merge, no rebase, no deploy, no discard**.

---

## Terminal summary

```
P3.7D.4 RECONCILIATION — AWAITING APPROVAL
Branch: release/p3-7b-staging @ 293dc668 (dirty; proxy uncommitted)
Verified Preview: dpl_G62cQNjWWFzRdwmxSW5MJDm8fJZG (CLI archive ≠ Git SHA)
Proposed: apps/web proxy + tests + security/deployment docs (+ fixed .gitignore)
Exclude: scripts evidence, env, playwright artifacts, unrelated trees
Tests: web 71, ui 24, tsc PASS, build PASS
Report: docs/deployment/P3-7D4-release-reconciliation.md
NO COMMIT / PUSH PERFORMED
```
