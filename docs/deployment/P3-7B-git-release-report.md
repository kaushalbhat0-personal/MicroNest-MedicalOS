# P3.7B — Git Release Report

**Date:** 2026-11-24  
**Verdict (Git):** **PASS**

| Item | Value |
|------|-------|
| Branch | `release/p3-7b-staging` |
| Base SHA | `2a0974e41af9e334e147794f45e258f34d6814d3` |
| Release commit | `9d3bedf11072298312e419cc020a93785026c64f` |
| Remote | `origin/release/p3-7b-staging` @ same SHA |
| `main` / `origin/main` | Unchanged at `2a0974e…` |
| Files in commit | **216** (+33230 / −1096) |
| `.env` committed | **No** |
| Force push | **No** |

## Included

- P3.6: server document keys + dental consent hard-gate + `tests/security/`
- Alembic **0018–0027** + companion modules/APIs/tests
- Web/UI companion surfaces, commercial/pilot/security docs

## Verification before commit

| Check | Result |
|-------|--------|
| P3.6 / document / dental / isolation / portal pytest | Green (~98) |
| Billing + scheduling + rx dental subset | Green |
| Ruff (router + dental focus) | Green after import order |
| Web/UI typecheck | Green |
| UI tests | 24 pass / 0 skip |
| Web production build | Green |
| Staged secret scan | Pass (only local test DB defaults in `tests/conftest.py`) |

## Preserved uncommitted locally

Ops scripts (`scripts/_p37*`), Playwright reports, `docs/ui-ux/`, `.env.example` dirty bits, etc.
