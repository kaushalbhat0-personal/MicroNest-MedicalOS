# P3.7B — Next Deployment Step

**Do not deploy until the blockers below are cleared.**

## Completed

1. Branch `release/p3-7b-staging` committed + pushed (`9d3bedf…`).  
2. Render service identified (`srv-dc2tmb49v7es73dkqc9g`, `https://micronest-medicalos.onrender.com`).  
3. Release verification tests green locally.

## Blockers

1. **API key scopes** — grant Services **Read & write** + Environment variables **Read & write**, **or** apply branch/env changes in the Render dashboard.  
2. Point service branch to `release/p3-7b-staging` and **disable auto-deploy**.  
3. Set required env vars (see `P3-7B-render-api-configuration.md`).  
4. Confirm build/start/health paths.

## Then (approved deploy phase)

1. Manual deploy of `release/p3-7b-staging` (still no auto-deploy).  
2. Smoke: `/api/healthz`, `/api/readyz`, auth, tenant, synthetic patient, document access, storage.  
3. Record results in `P3-7B-backend-smoke-test.md` / deployment report.  
4. Later: Vercel frontend + extend `ALLOWED_ORIGINS`.

## Explicit non-goals now

- No production deploy  
- No `main` push  
- No DB migrations on Render boot (staging already at 0027)  
- No BYPASSRLS changes  
- No SaaS payment live keys
