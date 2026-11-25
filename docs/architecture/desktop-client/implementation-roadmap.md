# Desktop implementation roadmap (Phase 1.1 → build phases)

Online-first. No offline clinical writes. No commit in this document phase.

**Critical path:** Auth backend (M2) → Foundation (M1 can start in parallel) → Shell (M3) → Nav (M4) → features by priority.

---

## Milestone summary

| # | Milestone | Parallelizable? | Depends on |
|---|-----------|-----------------|------------|
| 1 | Desktop project foundation | Yes (with M2 design) | Repo toolchain (Rust, Node) |
| 2 | Native authentication integration | Critical path | Backend B0 |
| 3 | Secure application shell | After M1+M2 | Credential store |
| 4 | Role-based navigation | After M3 | workspace-context |
| 5 | Dashboard | After M4 | appointment/ops APIs |
| 6 | Patient management | After M4 | patients APIs |
| 7 | Appointment calendar & reception | After M4 | scheduling APIs |
| 8 | Doctor clinical workspace | After M6 | encounters/Rx/dental |
| 9 | Billing & payments | After M4 | billing APIs |
| 10 | Inventory & workforce | After M4 | inventory/staff |
| 11 | Clinic settings | After M4 | tenants/admin APIs |
| 12 | E2E testing | Ongoing from M3 | staging synthetic |
| 13 | Windows packaging | After M3 minimal | Tauri bundler |
| 14 | Installer & update validation | After M13 | signing cert (ops) |
| 15 | Onboarding pilot acceptance | After M5–M9 core | signed staging build |

---

## M1 — Desktop project foundation

| | |
|--|--|
| **Scope** | Scaffold `apps/desktop` Tauri 2 + Vite React TS; consume `@healthcare-os/ui`; ban `next/*`; env/channel config stub |
| **Dependencies** | Rust stable, Node 24, WebView2 |
| **Backend** | None |
| **Frontend** | Empty shell route + token CSS import |
| **Security** | No secrets in repo; CSP draft |
| **Tests** | `npm run build` / `cargo check` |
| **Acceptance** | App window opens with Healthcare OS branded shell chrome (dev); CI builds unsigned debug |

## M2 — Native authentication integration

| | |
|--|--|
| **Scope** | Backend JSON login/refresh for `client_platform=windows`; desktop login UI; DPAPI refresh store; logout |
| **Dependencies** | M1; FastAPI session model |
| **Backend** | Extend auth/refresh; preserve cookies; tests |
| **Frontend** | Login screen; session bootstrap |
| **Security** | No token logs; DPAPI only for refresh |
| **Tests** | Backend auth tests; desktop login against staging synthetic user |
| **Acceptance** | Desktop obtains Bearer without cookie jar; web Playwright cookie auth still green |

## M3 — Secure application shell

| | |
|--|--|
| **Scope** | Toolbar, sidebar frame, online indicator, API client with Bearer + X-Tenant, error boundaries |
| **Dependencies** | M2 |
| **Backend** | None new |
| **Frontend** | Shell layout per design spec |
| **Security** | IPC allowlist; TLS only |
| **Tests** | Unit: api client auth header injection |
| **Acceptance** | Authenticated empty home; offline shows blocking reconnect |

## M4 — Role-based navigation

| | |
|--|--|
| **Scope** | Port `NAV_RULES` / `filterNavByPermissions`; role default homes |
| **Dependencies** | M3; `workspace-context` |
| **Backend** | None |
| **Frontend** | Permission-filtered nav; unify Staff (drop Team dup) |
| **Security** | UI hide ≠ authz |
| **Tests** | Port `nav.test.ts` logic |
| **Acceptance** | doctor vs receptionist vs tenant_admin see different nav on synthetic seeds |

## M5 — Dashboard

| | |
|--|--|
| **Scope** | Today’s appointments, key counts, jumps to reception/schedule |
| **Dependencies** | M4 |
| **Backend** | Existing dashboard/ops endpoints |
| **Frontend** | Port/adapt `/` + ops widgets |
| **Security** | No PHI in window titles/logs |
| **Tests** | E2E smoke synthetic |
| **Acceptance** | Matches web data for same user/tenant |

## M6 — Patient management

| | |
|--|--|
| **Scope** | Directory, create, search, Patient 360 tabs (read/update per perms) |
| **Dependencies** | M4 |
| **Backend** | Existing patients APIs |
| **Frontend** | Adapt patients pages to SPA router |
| **Security** | Tenant header always set |
| **Tests** | E2E create+open patient |
| **Acceptance** | CRUD parity with web for receptionist seed |

## M7 — Appointment calendar & reception

| | |
|--|--|
| **Scope** | Schedule views, book/reschedule/cancel, reception queue, check-in |
| **Dependencies** | M4; ideally M6 for patient picker |
| **Backend** | Existing scheduling |
| **Frontend** | Adapt schedule + reception |
| **Security** | — |
| **Tests** | E2E book + check-in |
| **Acceptance** | Queue updates match API; no offline queue |

## M8 — Doctor clinical workspace

| | |
|--|--|
| **Scope** | Encounter list/detail, notes, dx, Rx, dental chart/plans |
| **Dependencies** | M6 |
| **Backend** | Existing clinical modules |
| **Frontend** | Adapt encounters + dental |
| **Security** | Extra care on logs/screenshots in tests |
| **Tests** | E2E open encounter; sign Rx if permitted |
| **Acceptance** | Doctor completes documented visit online |

## M9 — Billing & payments

| | |
|--|--|
| **Scope** | Invoices, estimates, payments, catalog entry points |
| **Dependencies** | M4; M6 helpful |
| **Backend** | Existing billing |
| **Frontend** | Adapt billing routes; nav subitems |
| **Security** | Money display server-authoritative |
| **Tests** | E2E record payment synthetic |
| **Acceptance** | Payment appears on invoice as on web |

## M10 — Inventory & workforce

| | |
|--|--|
| **Scope** | Inventory tabs; staff directory/invites/attendance/leave |
| **Dependencies** | M4 |
| **Backend** | Existing |
| **Frontend** | Adapt inventory + staff |
| **Security** | — |
| **Tests** | Smoke per role |
| **Acceptance** | tenant_admin manages invite; inventory adjust with perm |

## M11 — Clinic settings

| | |
|--|--|
| **Scope** | Locations, roles, audit viewer, practitioners, sessions |
| **Dependencies** | M4 |
| **Backend** | Existing; note `settings.manage` gap |
| **Frontend** | Adapt admin + sessions |
| **Security** | Session revoke works for desktop tokens |
| **Tests** | Revoke session → desktop re-auth |
| **Acceptance** | Admin can revoke; desktop loses access on refresh |

## M12 — E2E testing

| | |
|--|--|
| **Scope** | Desktop WebDriver/Playwright against Tauri or bundled webview; synthetic only |
| **Dependencies** | From M3 onward |
| **Acceptance** | CI suite gates staging desktop channel |

## M13 — Windows packaging

| | |
|--|--|
| **Scope** | NSIS per-user installer; versioning; About dialog |
| **Dependencies** | M3+ |
| **Acceptance** | Unsigned local install works on clean Windows 10/11 VM |

## M14 — Installer & update validation

| | |
|--|--|
| **Scope** | Authenticode; updater staging feed; rollback drill |
| **Dependencies** | Org cert; M13 |
| **Acceptance** | Signed install; update applies; bad signature rejected |

## M15 — Onboarding pilot acceptance

| | |
|--|--|
| **Scope** | One synthetic/pilot clinic: reception + doctor + admin happy path |
| **Dependencies** | M5–M9, M14 staging |
| **Acceptance** | Signed checklist signed-off; no PHI in logs; web still primary fallback |

---

## Explicit non-goals until later major phase

- Offline clinical writes / local patient DB / sync engine  
- Patient PWA implementation  
- Dual Android full client  
- Subscription/payment infrastructure changes  
- Automatic WhatsApp messaging
