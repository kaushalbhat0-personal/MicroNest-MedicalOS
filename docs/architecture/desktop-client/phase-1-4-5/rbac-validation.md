# RBAC Validation — Desktop M5/M6

## Principles

1. Navigation uses `workspace-context.permissions` (UX only).
2. Every data call goes through authenticated `apiFetch` with tenant header.
3. 401 → session expired flow; 403 → error or section omitted (never invent data).
4. Workspace switch / logout clears `patientViewId` and returns to dashboard route.

## Permission map

| Capability | Permission | UI gate |
|------------|------------|---------|
| See Patients nav | `patient.read` | `nav.ts` |
| Register | `patient.create` | Register card hidden if missing |
| Edit demographics | `patient.update` | Read-only DL if missing |
| See Schedule/Reception nav | `appointment.read` | `nav.ts` |
| Book / walk-in | `appointment.create` | Forms hidden if missing |
| Status / cancel / reschedule | `appointment.update` | Actions hidden if missing |

## Catalog permissions unused by these APIs

`schedule.manage`, `queue.manage` — exist in permission catalog but **not** attached to scheduling HTTP adapters. Desktop does not claim them.

## Client role distrust

`dashboardVariant(role)` is presentation only. Doctors without `patient.read` cannot open directory via nav; if deep-linked, API 403 surfaces.

## Cross-tenant

Evidence script probes foreign tenant id → blocked (401/403/404). Backend isolation suite: `tests/isolation/test_scheduling_isolation.py`.
