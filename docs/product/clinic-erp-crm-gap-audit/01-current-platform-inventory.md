# 01 — Current platform inventory

Evidence from `backend/app/`, `apps/web/`, `packages/ui/`, `tests/`, Alembic `0001`–`0017`.

## Backend modules

| Module | Path | State |
|--------|------|--------|
| Identity / sessions | `modules/identity/` | Shipped (P1) |
| Tenancy / memberships / roles | `modules/tenancy/` | Shipped (P1) |
| Clinics / locations | `modules/clinics/` | Shipped — timezone only, no hours |
| Audit + outbox | `modules/audit/`, `platform/events/` | Shipped |
| Notifications (request + eligibility) | `modules/notifications/` | Partial — adapters are console/none |
| Patients | `modules/patients/` | Minimal identity |
| Scheduling | `modules/scheduling/` | P2 complete for staff booking |
| Clinical | `modules/clinical/` | P3 encounters/notes/vitals/dx |
| Prescriptions | `modules/prescriptions/` | P3 signed lifecycle |
| Dental | `modules/dental/` | P3 findings/plans/consents/recalls/docs refs |
| Billing | `modules/billing/` | P4 catalog→estimate→invoice→pay→refund |
| Portal links | `modules/portal/` | P6 enroll/revoke + projections |
| Workspaces / specialties | `modules/workspaces/` | O1.2 registry + provision |
| Subscriptions | `modules/subscriptions/` | O1.3R visibility |
| Inventory | `modules/inventory/__init__.py` | Stub only |
| Documents (domain) | `modules/documents/__init__.py` | Stub; dental `document_references` exists |
| Reports | `modules/reports/__init__.py` | Stub |
| Branding / licensing / encounters pkg | stubs | Declared only |

## API routers (`api/v1/router.py`)

Mounted: auth, account, invites, signup, platform, tenants, workspaces, audit, patients, scheduling, encounters, prescriptions, dental, billing, portal.

## Frontend surfaces (`apps/web`)

| Surface | Routes | Notes |
|---------|--------|--------|
| Clinic workspace | `/`, `/reception`, `/patients`, `/schedule`, `/encounters`, `/dental/*`, `/billing/*`, `/team`, `/admin`, `/sessions` | Nav in `lib/nav.ts` |
| Patient portal | `/portal/*` | Same Next app; not `apps/patient-portal` |
| Platform admin | `/platform/tenants/*` | Read-only console |
| Auth | `/login`, `/signup`, `/verify` | Frictionless identity |

`apps/patient-portal/` and `apps/platform-admin/` exist as package shells; primary UX is in `apps/web`.

## Design system

`DESIGN.md` + `packages/ui` — clinic operational UI must stay token-based (no redesign of unrelated pages).

## Test inventory (high signal)

- Scheduling: `tests/api/test_appointments_api.py`, `test_appointment_concurrency.py`, `tests/service/test_scheduling.py`, `tests/isolation/test_scheduling_isolation.py`
- Clinical/dental: `test_clinical_api.py`, `test_dental_api.py`, `test_clinical_isolation.py`
- Billing: `test_billing_*`, `tests/service/test_*`
- Portal: `tests/portal/test_portal_security.py`, `test_portal_flows.py`, `test_portal_workspaces.py`, `test_portal_link_rls.py`
- Two-tenant: `test_p8_two_tenant_pilots.py`, `test_o15r_two_pilot_e2e.py`

**Gap:** no dedicated `tests/api/test_patients_api.py` — patients are only exercised as fixtures elsewhere.
