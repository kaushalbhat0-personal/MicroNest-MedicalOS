# Known Limitations — M10

| Item | Status | Notes |
|------|--------|-------|
| Tenant-wide refund list | **NOT IMPLEMENTED** | No API; patient + payment scoped |
| Tenant-wide credit-note list | **NOT IMPLEMENTED** | No API; patient + invoice scoped |
| Dedicated `refundable_amount` on PaymentResponse | **PARTIALLY_SUPPORTED** | Display hint = allocated + unallocated |
| Refund void / reverse | **NOT IMPLEMENTED** | Issued refunds immutable |
| Void issued credit note | **NOT IMPLEMENTED** | Draft void only |
| Credit note as cash refund | N/A | Distinct semantics; UI captions |
| Clinic reconciliation HTTP | **NOT IMPLEMENTED** | M8 backlog |
| PDF invoice / CN render | **NOT IMPLEMENTED** | M8 backlog |
| Estimate timeline events | Incomplete | M8 backlog |
| Online payment gateways | Out of scope | Manual/offline only |
| Filmed EXE click-through | **PARTIAL** | Debug EXE + API evidence |
| M9 leave cancel / balances | Backlog | Unchanged |
