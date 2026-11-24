# 02 — Patient CRM gaps

## Model today

`backend/app/modules/patients/models.py` — tenant-owned identity only:

`id`, `tenant_id`, `display_name`, `phone?`, `is_active`, timestamps.

Decision record: `docs/decisions/P2-01-scheduling-model.md` deliberately kept demographics out of v1.

## Capability matrix

| Capability | Classification | Evidence |
|------------|----------------|----------|
| Register patient (name + phone) | **IMPLEMENTED AND VERIFIED** | `POST …/patients` in `api/v1/patients.py`; used across scheduling/billing/portal tests; UI `apps/web/app/patients/page.tsx` |
| List patients | **IMPLEMENTED BUT NEEDS IMPROVEMENT** | `list_patients` limit≤200, no search, no cursor; client-side filter only on loaded page |
| Get patient by id | **IMPLEMENTED AND VERIFIED** | `GET …/patients/{id}` + tenant 404-oracle |
| Update patient | **MISSING** | `P.PATIENT_UPDATE` declared in `permissions.py` but **not in any seed role** and **no PATCH route** |
| Server-side search | **MISSING** | No `q=` / ILIKE; UI says “filter the loaded list” |
| Duplicate detection | **MISSING** | No unique phone constraint; no soft-match warning |
| Email / demographics / DOB | **MISSING** | Not on model/schema |
| Emergency contacts | **MISSING** | — |
| Communication preferences | **MISSING** | Eligibility expects consent snapshot; no patient prefs table |
| Patient-clinic relationship | **IMPLEMENTED AND VERIFIED** | Tenant ownership via `tenant_id` + RLS; memberships separate |
| Portal user linkage | **IMPLEMENTED AND VERIFIED** | `portal_links` + enroll (`modules/portal/service.py`); staff-gated |
| Patient status (active) | **PARTIALLY IMPLEMENTED** | `is_active` on create=true; no staff API to deactivate |
| Activity history | **PARTIALLY IMPLEMENTED** | Audit `patient.register` only; no CRM activity feed |
| Follow-up tracking | **PARTIALLY IMPLEMENTED** | Dental `recalls` only — not generic CRM |
| Segmentation | **MISSING** | — |
| Merge / correction | **MISSING** | — |
| CSV / Excel import | **MISSING** | No import endpoint; pilot cannot migrate register |
| Export | **MISSING** | `REPORTS_EXPORT` declared, unused |
| Dedicated patient API tests | **MISSING** | No `test_patients_api.py` |

## Excel register replacement verdict

**Cannot replace Excel today.** Clinics need at least: searchable register, editable contacts, basic demographics, duplicate warning, import, and status management — all on the existing `patients` table (no second model).

## Priority

| Item | Priority |
|------|----------|
| Update + deactivate + search | **P0** — addressed in slice `0018` + patients API/UI |
| Email + emergency contact + DOB | **P0** — addressed in slice `0018` |
| Soft duplicate check on phone/email | **P0** — soft `potential_duplicates` + import skip |
| CSV import | **P0** — `POST …/patients/import` + patients UI paste import |
| Communication prefs / merge / segmentation | **P1–P3** — still open |

**Post-slice note:** classifications above describe the audited baseline at `2a0974e`. The first vertical slice implements the P0 CRM rows; prefs/merge/segmentation remain open.