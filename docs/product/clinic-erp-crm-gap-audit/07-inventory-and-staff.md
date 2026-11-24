# 07 — Inventory and staff

## Inventory

| Capability | Classification | Evidence |
|------------|----------------|----------|
| Products / stock / movements | **MISSING** | `modules/inventory/__init__.py` stub |
| Low-stock / suppliers / expiry | **MISSING** | Permissions declared only |
| Inventory module | **OUT OF SCOPE** for pilot P0 | Explicit P4+ stub |

## Staff

| Capability | Classification | Evidence |
|------------|----------------|----------|
| Invitations | **IMPLEMENTED AND VERIFIED** | invites API + team UI |
| Roles / permissions | **IMPLEMENTED AND VERIFIED** | `permissions.py` + custom roles |
| Membership list / activate | **IMPLEMENTED AND VERIFIED** | Team page |
| Location assignment API | **IMPLEMENTED BUT NEEDS IMPROVEMENT** | API supports `location_ids`; Team UI does not expose |
| Practitioner profiles + verification | **IMPLEMENTED AND VERIFIED** | Required for booking |
| Working hours | **PARTIALLY IMPLEMENTED** (post-slice) | `location_working_hours` + schedule UI Mon–Sat template; no per-practitioner rota |
| Attendance | **MISSING** | — |
