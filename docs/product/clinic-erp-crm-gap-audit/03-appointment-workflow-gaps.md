# 03 — Appointment / scheduling workflow gaps

Authority: `docs/decisions/P2-01-scheduling-model.md`, `modules/scheduling/`, `api/v1/scheduling.py`, reception/schedule UI, pytest suites.

## Capability matrix

| Capability | Classification | Evidence |
|------------|----------------|----------|
| Staff booking | **IMPLEMENTED AND VERIFIED** | `create_appointment`; `test_appointments_api.py`; UI `schedule/page.tsx` |
| Duration bounds | **IMPLEMENTED AND VERIFIED** | 5–480 min in schema/service |
| Reschedule | **IMPLEMENTED BUT NEEDS IMPROVEMENT** | Service + UI; HTTP coverage thin vs create/cancel |
| Cancel | **IMPLEMENTED AND VERIFIED** | Service + API + portal cancel |
| Status lifecycle | **IMPLEMENTED AND VERIFIED** | `TRANSITIONS`; reception check-in; no-show; completed |
| Check-in | **IMPLEMENTED AND VERIFIED** | `reception/page.tsx` → `POST …/status` |
| Waiting queue product | **PARTIALLY IMPLEMENTED** | Today’s list ordered by time; no queue tokens / `QUEUE_MANAGE` |
| Double-booking prevention | **IMPLEMENTED AND VERIFIED** | Advisory lock + overlap; `test_appointment_concurrency.py` |
| Timezone handling | **IMPLEMENTED AND VERIFIED** | Location IANA + UTC storage |
| Idempotency | **IMPLEMENTED AND VERIFIED** | Header/body key + partial unique |
| Doctor-wise list filter | **IMPLEMENTED AND VERIFIED** | `practitioner_id` query param |
| Calendar day/week/month views | **MISSING** | Table/list only — no calendar grid |
| Doctor/location working hours | **MISSING** | Location has `timezone` only (`clinics/models.py`) |
| Slot / availability discovery | **MISSING** | Overlap check only; no free-slot API |
| Walk-in semantics | **MISSING** | `enforce_future=True` blocks “now”; no walk-in flag |
| Follow-up appointment link | **MISSING** | No parent_appointment_id / recall→booking |
| Booking audit | **IMPLEMENTED AND VERIFIED** | `appointment.create/reschedule/status/cancel` audit refs |
| Patient self-booking | **MISSING** | Portal has list + cancel only (`portal.py`, appointments UI copy) |
| Safe public availability | **MISSING** | Must be designed so slots never leak other patients |

## Reuse rule

Do **not** create a parallel appointment table or router. Extend `modules/scheduling` and portal adapters only.

## Post-slice note (`0018` + scheduling/portal)

Addressed from this matrix: location working hours, free-slot availability API, walk-in create (`walk_in`), patient self-book via `POST /portal/appointments`. Still open: calendar grids, queue tokens, follow-up appointment linking, patient reschedule.