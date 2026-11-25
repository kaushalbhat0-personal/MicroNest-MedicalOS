# M8 Billing API Audit

**Branch:** `release/p3-7b-staging` @ `293dc66`  
**Date:** 2026-11-25  
**Source:** `backend/app/api/v1/billing.py`, `backend/app/modules/billing/`

## Money rules

- Amounts are **string decimals** (never invent totals in the UI).
- Currency: **INR** only at validation.
- Invoice paid portion = `allocated_amount`; collectible = `outstanding_amount`.
- No `amount_paid` field — use `allocated_amount`.

## Workflow matrix

| Workflow | Existing API | Permission | Financial rules | Tests | Desktop status |
|----------|--------------|------------|-----------------|-------|----------------|
| Estimate list/get | GET `/estimates`, `/estimates/{id}` | `billing.read` | status filter, cursor | `test_billing_estimates_api.py` | Implemented |
| Estimate issue | POST `.../issue` | `billing.create` | draft→issued; valid_until | same | Implemented |
| Estimate cancel/expire | POST cancel/expire | `billing.create` | transition map | same | Implemented |
| Estimate convert | POST `.../convert` | `billing.create` | issued/converted; advisory lock; creates **draft** invoice | invoices convert tests | Implemented |
| Invoice list/get | GET `/invoices` | `billing.read` | `allocated_amount`, `outstanding_amount` | `test_billing_invoices_api.py` | Implemented |
| Invoice issue/void | POST issue/void | `invoice.issue` | FY numbering; void needs no settlement | same | Implemented |
| Payment record | POST `/payments` | `payment.record` | cash/upi/manual_card/manual_other; Idempotency-Key | `test_billing_payments_api.py` | Implemented |
| Allocate | POST `.../allocations` | `payment.record` | cannot exceed unallocated or outstanding | same | Implemented |
| Invoice balance | GET `.../balance` | `billing.read` | authoritative | same | Implemented |
| Patient overview AR | GET patient overview | `patient.read` | `outstanding_balance` | patient 360 | Implemented |
| Credit balance | GET `.../credit-balance` | `billing.read` | unallocated sum | payments service | Implemented |
| Refunds | POST `.../refunds` | `billing.refund` | supported but **out of M8 primary UI** (documented) | adjustments API | Not primary UI |
| Clinic reconciliation API | **MISSING** | — | service-level test only | `test_outstanding_aggregate_reconcile.py` | Read-only ops aggregate only |
| Patient AR aging list | **MISSING** | — | build from invoice list + outstanding | — | Outstanding dues via invoice filter |

## Estimate transitions

`draft` → `issued` | `cancelled`  
`issued` → `converted` | `expired` | `cancelled`  
Terminal: `converted`, `expired`, `cancelled`

## Invoice transitions

Manual: `draft` → `issued` | `voided`  
Payment-derived: `issued` ↔ `partially_paid` ↔ `paid`  
Void issued requires zero allocations + no credit notes.

## Payment methods

`cash`, `upi`, `manual_card`, `manual_other` — offline/manual recording only (no gateway).

## Ambiguous / unsupported (do not invent)

1. No clinic reconciliation HTTP API — show ops dashboard outstanding aggregate only.
2. No dedicated AR aging endpoint — dues workspace uses invoice list filtered by outstanding.
3. Timeline omits estimate events.
4. Refunds/credit notes exist but are out of primary M8 UX (not gateway; optional later).
5. Convert produces **draft** invoice — still needs `invoice.issue` to number/finalize.
