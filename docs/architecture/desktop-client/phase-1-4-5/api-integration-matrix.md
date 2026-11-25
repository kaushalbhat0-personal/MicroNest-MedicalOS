# API Integration Matrix — Phase 1.4+1.5

| Feature | UI | Endpoint | Permission | Backend test | Desktop test |
|---------|-----|----------|------------|--------------|--------------|
| Patient list | PatientsDirectory | `GET /tenants/{t}/patients?q&limit&active_only` | `patient.read` | `test_patients_api.py` | unit nav + API evidence |
| Patient create | Register form | `POST /tenants/{t}/patients` | `patient.create` | `test_patients_api.py` | API evidence |
| Patient get | PatientProfile | `GET /tenants/{t}/patients/{id}` | `patient.read` | `test_patients_api.py` | API evidence |
| Overview | Profile cards | `GET .../patients/{id}/overview` | `patient.read` | `test_patient_360.py` | API evidence |
| Timeline | History tab | `GET .../timeline?category&cursor&limit` | `patient.read` | `test_patient_360.py` | API evidence |
| Patient patch | Demographics | `PATCH .../patients/{id}` | `patient.update` | `test_patients_api.py` | API evidence |
| Soft duplicates | Register/edit alert | `potential_duplicates` on create/patch | n/a (response field) | `test_patients_api.py` | API evidence |
| Appointments list | Calendar | `GET .../appointments?start_from&start_to&...` | `appointment.read` | `test_appointments_api.py` | API evidence |
| Availability | Book slots | `GET .../availability?practitioner_id&location_id&day` | `appointment.read` | `test_availability_api.py` | API evidence |
| Create appt | Book / walk-in | `POST .../appointments` | `appointment.create` | `test_appointments_api.py` | API evidence |
| Reschedule | Detail | `PATCH .../appointments/{id}` | `appointment.update` | `test_appointments_api.py` | transition unit |
| Status | Detail / queue | `POST .../appointments/{id}/status` | `appointment.update` | `test_appointments_api.py` | `schedulingApi.test.ts` |
| Cancel | ConfirmDialog | `POST .../appointments/{id}/cancel` | `appointment.update` | `test_appointments_api.py` | UI wired |
| Reception queue | Reception | `GET .../locations/{loc}/reception-queue?day` | `appointment.read` | `test_reception_queue.py` | API evidence |
| Practitioners | Filters | `GET .../practitioners` | (staff read as returned) | scheduling tests | UI wired |
| Locations | Filters | `GET .../locations` | `tenant.read` / locations | ops tests | UI wired |
| Related 360 lists | Profile tabs | encounters, plans, invoices, payments, follow-ups, consents | respective `*.read` | module tests | softGet 403 omit |
| Cross-tenant | n/a | wrong `X-Tenant` / tenant path | isolation | `test_scheduling_isolation.py` | API evidence |

All calls use desktop `apiFetch` (Bearer + `X-Tenant`) via Tauri host-allowlisted `api_request`.
