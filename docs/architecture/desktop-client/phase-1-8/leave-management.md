# Leave Management

## Screen

`StaffHub` → **Leave** tab

## API

| Action | Endpoint | Permission |
|--------|----------|------------|
| Leave types | `GET /tenants/{id}/leave-types` | `tenant.read` |
| List requests | `GET /tenants/{id}/leave-requests?membership_id&status` | `tenant.read` / manage |
| Create | `POST /tenants/{id}/leave-requests` | authenticated staff |
| Decide | `POST /tenants/{id}/leave-requests/{id}/decide` | `staff.manage` |
| Cancel | **NO HTTP** | service-only / gap |

## Supported UX

- Create request: leave type, start/end dates, reason  
- Pending / history filters  
- Approve / reject with ConfirmDialog + optional note  

## NOT IMPLEMENTED

| Capability | Status |
|------------|--------|
| Leave cancel via HTTP | **NOT IMPLEMENTED** |
| Leave balances / accrual | **NOT IMPLEMENTED** |

Desktop captions these gaps; UI does not fake cancel or balances.

## Self-approval

Desktop does not special-case self-approval. Evidence: synthetic admin deciding **own** leave → HTTP **403** (`leave_self_decide_observed: false`). Manager decide on other memberships remains covered by `tests/api/test_staff.py`.

## State transitions

`pending` → `approved` | `rejected`

## Tests

- Backend: `test_staff.py` leave  
- Desktop: Leave tab; evidence create/decide + cancel 404 documented
