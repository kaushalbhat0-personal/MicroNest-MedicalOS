# Healthcare OS — Phase 1.1 Desktop EXE Architecture & Clinic Workflow Blueprint

**Phase:** 1.1 — architecture / UX / auth / packaging blueprint only  
**Date:** 2026-11-25  
**Branch audited:** `release/p3-7b-staging` @ `293dc66` (+ preserved dirty tree; no commit/push)  
**Product decision (locked):** Clinic Windows desktop is **online-first**. No offline clinical writes, no local patient DB, no sync engine in first release.

## Overall verdict

**READY TO PLAN IMPLEMENTATION — NOT READY TO SHIP.**

| Gate | Status |
|------|--------|
| Clinic feature surface exists on web + FastAPI | **PASS** (mapped) |
| DESIGN.md + `@healthcare-os/ui` reusable for desktop shell | **PASS** |
| Tauri 2 + Vite SPA architecture validated vs constraints | **PASS** (recommended) |
| Native login/refresh JSON tokens on production FastAPI | **BLOCKED** (cookies-only today) |
| Tauri EXE / installer exists | **NOT CLAIMED** — none built this phase |
| Offline / encrypted local DB for v1 | **OUT OF SCOPE** (architecture reserved for later) |

## Product split

| Client | Stack | Audience |
|--------|-------|----------|
| **Clinic Desktop EXE** (priority) | Tauri 2 + React/Vite + `@healthcare-os/ui` → FastAPI | Doctors, reception, owners, admins, staff |
| **Patient Mobile PWA** | Existing Next.js `/portal/*` (improve later) | Patients |
| **Clinic Web** (retained) | Next.js `apps/web` on Vercel | Same clinic roles in browser |

Same backend, RBAC, tenancy, audit. No second authorization system. No embedded second backend.

## Documents

1. [existing-application-audit.md](./existing-application-audit.md)  
2. [desktop-architecture.md](./desktop-architecture.md)  
3. [desktop-information-architecture.md](./desktop-information-architecture.md)  
4. [role-workflow-matrix.md](./role-workflow-matrix.md)  
5. [desktop-design-specification.md](./desktop-design-specification.md)  
6. [authentication-integration-plan.md](./authentication-integration-plan.md)  
7. [packaging-and-security.md](./packaging-and-security.md)  
8. [patient-pwa-boundary.md](./patient-pwa-boundary.md)  
9. [implementation-roadmap.md](./implementation-roadmap.md)  
10. [acceptance-matrix.md](./acceptance-matrix.md)  

Related prior work (unchanged; not overwritten):

- `docs/architecture/native-client-poc/` — A1/A2 PoCs (DPAPI proven; Tauri not built)  
- `docs/architecture/windows-desktop-architecture.md` — A0 (offline-oriented; **superseded for v1 scope** by Phase 1.1 online-first)  

## Exact next implementation phase

**Phase 1.2 — Backend native session contract + desktop project foundation**

1. Extend FastAPI login/refresh for device-aware **JSON** tokens (preserve web cookies).  
2. Scaffold `apps/desktop` (Tauri 2 + Vite) consuming `@healthcare-os/ui` — **no feature parity yet**.  
3. Secure shell + DPAPI-backed refresh storage + online API client with `Authorization` + `X-Tenant`.  

Do **not** implement offline sync, patient PWA changes, or production signing keys in 1.2 without explicit approval.

## Safety

- No commit, push, deploy, Docker, or production/staging infra changes in Phase 1.1.  
- Native experiments under `experiments/native-client-poc/` preserved.  
- Web release reconciliation (P3.7D.4) remains separate.
