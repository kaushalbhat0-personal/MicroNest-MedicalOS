# M4 — Desktop shell report

**Verdict: PASS** (shell + permission-filtered nav + API dashboards; full clinical modules out of scope)

## Shell

- Sidebar with grouped nav (Overview / Patient Care / Clinical / Clinic Operations / Workspace)  
- Top toolbar: clinic name, user, role, notifications placeholder, switch clinic, verify session, logout  
- Breadcrumbs, main content, loading/empty/error/session-expired states  
- Reuses `@healthcare-os/ui` (Button, Field, Input, Card, Alert, EmptyState, ErrorState, LoadingState)

## Role-based navigation

Port of `apps/web/lib/nav.ts` rules in `apps/desktop/src/lib/nav.ts`.  
Permissions from `GET /tenants/{id}/workspace-context` only.

Unit tests: 6/6 PASS (`nav.test.ts`).

## Dashboards (existing operations API)

`GET /tenants/{tenant_id}/locations/{location_id}/operations-dashboard`

| Variant | Trigger | Content |
|---------|---------|---------|
| Doctor | role doctor/nurse or clinical perms | Today metrics, waiting, next appointments table |
| Receptionist | role receptionist | Queue-oriented metrics + token column + deferred quick-action note |
| Admin | tenant_admin / staff.manage | Ops metrics + billing attention + admin shortcut visibility |
| Generic | fallback | Same ops snapshot when permitted |

No invented metrics — sections omitted by server when permission missing (`sections_omitted`).

## Deferred module routes

Patients, schedule, reception, etc. show placeholders; nav remains permission-filtered. Backend still enforces every API.
