# Phase 1.8 — M9 Staff and Workforce Management

**Date:** 2026-11-25  
**Branch:** `release/p3-7b-staging` @ `293dc66` (no commit/push)

## Verdicts

| Gate | Verdict |
|------|---------|
| Overall | **CONDITIONAL PASS** |
| M9 Workforce workflows | **PASS** (supported APIs only) |
| Leave cancel HTTP | **NOT IMPLEMENTED** (backend gap) |
| Leave balances / accrual | **NOT IMPLEMENTED** (backend gap) |
| Schedule PATCH | **NOT IMPLEMENTED** (create + deactivate only) |
| Interactive EXE filmed click-through | **PARTIAL** (debug EXE + API evidence) |
| Production readiness | **FAIL** (not claimed) |

## Documents

1. [M9-workforce-api-audit.md](./M9-workforce-api-audit.md)
2. [staff-directory-and-profiles.md](./staff-directory-and-profiles.md)
3. [invitations-and-rbac.md](./invitations-and-rbac.md)
4. [practitioner-management.md](./practitioner-management.md)
5. [staff-schedules.md](./staff-schedules.md)
6. [attendance-management.md](./attendance-management.md)
7. [leave-management.md](./leave-management.md)
8. [workforce-overview.md](./workforce-overview.md)
9. [security-and-tenant-isolation.md](./security-and-tenant-isolation.md)
10. [test-evidence.md](./test-evidence.md)
11. [known-limitations.md](./known-limitations.md)

Evidence: [evidence/m9_workforce_evidence.json](./evidence/m9_workforce_evidence.json)

## Desktop surface

| Route | Component |
|-------|-----------|
| `/staff` | `StaffHub` — Overview, Directory, Invitations, Practitioners, Schedules, Attendance, Leave |

API client: `apps/desktop/src/lib/staffApi.ts`

## Exact next milestone

**M10** product choice — deepen dental charting, refunds/credit-notes UX, or offline-capable sync spikes. Payroll, biometrics, GPS attendance, and automated WhatsApp remain out of scope.
