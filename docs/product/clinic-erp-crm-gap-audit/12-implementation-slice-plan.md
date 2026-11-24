# 12 — Implementation slice plan (Stage 2–3)

## Selected slice

**Patient CRM foundation + availability + portal booking + profile enrichment**

Reuse: `patients`, `scheduling`, `portal`, reception/schedule UI, existing concurrency locks.

## Existing modules reused

| Area | Reuse |
|------|--------|
| Patient identity table | Extend columns; no second model |
| Appointments | `create_appointment` / cancel / overlap lock |
| Portal context | `portal_ctx` + link ownership |
| Audit / outbox | Refs-only append on register/update/book |
| Permissions catalog | Extend seeds + new `portal.appointment.book` |

## Missing components to add

1. Patient fields: `email`, `date_of_birth`, `emergency_contact_name`, `emergency_contact_phone`
2. `update_patient`, `search` (`q`), soft `find_potential_duplicates`
3. CSV import (`POST …/patients/import`) — staff `patient.create`
4. `location_working_hours` table (weekday + local start/end + slot minutes)
5. Availability service: generate slots from hours − live appointments
6. Staff + portal availability GET; portal book POST
7. Walk-in flag on staff create (`allow_past` / start→checked_in)
8. UI: patients list/search/edit/import; schedule hours hint; portal book flow; profile appointments + wa.me
9. Tests: patients API, availability privacy, portal book concurrency, migration down

## API changes

- `PATCH /tenants/{tid}/patients/{id}`
- `GET /tenants/{tid}/patients?q=`
- `POST /tenants/{tid}/patients/import`
- `GET/PUT /tenants/{tid}/locations/{lid}/working-hours`
- `GET /tenants/{tid}/availability`
- `GET /portal/bookable-practitioners` (minimal: id + display name of verified practitioners with hours)
- `GET /portal/availability`
- `POST /portal/appointments` (book)
- Staff create appointment: optional `walk_in: true`

## Schema / migration

- `0018_patient_crm_availability.py`
  - alter `patients` add columns (nullable)
  - create `location_working_hours`
  - seed role permission updates (`patient.update`, `portal.appointment.book`)
  - downgrade drops columns/table and restores prior permission sets where practical

## Authorization

- Staff patient update: `patient.update` (seed: tenant_admin, receptionist; doctor read-only remains)
- Portal book: `portal.appointment.book` + active portal link; `patient_id` server-derived
- Availability: portal returns slots only; staff may see same slots with tenant auth

## UI routes

- Enhance `/patients`, `/patients/[id]`
- Portal `/portal/appointments` booking panel
- Optional working-hours editor on admin or schedule (minimal)

## Test plan

- `tests/api/test_patients_api.py`
- `tests/api/test_availability_api.py`
- `tests/portal/test_portal_booking.py`
- Extend concurrency for portal book
- OpenAPI contract path updates
- Migration upgrade/downgrade

## Rollback

- Alembic downgrade 0018
- Feature is additive; disabling portal book permission removes self-service without breaking staff scheduling

## Explicitly not in this slice

Calendar grid, inventory, automated WhatsApp, ophthalmology, D2 annotation, PDF billing, notification consent DB, queue tokens.
