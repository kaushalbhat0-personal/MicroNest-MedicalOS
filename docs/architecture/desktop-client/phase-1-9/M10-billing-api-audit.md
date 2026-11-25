# M10 Billing API Audit — Refunds & Credit Notes

**Branch:** `release/p3-7b-staging` @ `293dc66`  
**Date:** 2026-11-25  
**Rule:** Endpoint existence required; models alone are insufficient.

## Capability matrix

| Capability | Backend support | Permission | Desktop status | Decision |
|------------|-----------------|------------|----------------|----------|
| Create refund (full/partial) | `POST .../payments/{id}/refunds` | `billing.refund` | Implement | **SUPPORTED** |
| List refunds for payment | `GET .../payments/{id}/refunds` | `billing.read` | Implement | **SUPPORTED** |
| Get refund by id | `GET .../refunds/{id}` | `billing.read` | Detail via list | **SUPPORTED** |
| Tenant-wide refund list | **MISSING** | — | Exclude | **NOT_IMPLEMENTED** |
| Dedicated `refundable_amount` field | **MISSING** (derived server-side) | — | Display hint = `allocated + unallocated` (= `amount − refunded`) | **PARTIALLY_SUPPORTED** |
| Over-refund rejection | ValidationError | — | Show API error | **SUPPORTED** |
| Idempotent refund | body/`Idempotency-Key` | — | body key | **SUPPORTED** |
| Refund void/reverse | **MISSING** (issued immutable) | — | Exclude | **NOT_IMPLEMENTED** |
| Gateway/bank settlement | Not modeled | — | Caption only | **NOT_IMPLEMENTED** |
| Create credit note draft | `POST .../invoices/{id}/credit-notes` | `billing.refund` | Implement | **SUPPORTED** |
| Issue credit note | `POST .../credit-notes/{id}/issue` | `billing.refund` | Implement | **SUPPORTED** |
| Void draft credit note | `POST .../credit-notes/{id}/void` | `billing.refund` | Implement | **SUPPORTED** |
| List CNs for invoice | `GET .../invoices/{id}/credit-notes` | `billing.read` | Implement | **SUPPORTED** |
| Get CN by id | `GET .../credit-notes/{id}` | `billing.read` | Detail via list | **SUPPORTED** |
| Tenant-wide CN list | **MISSING** | — | Exclude | **NOT_IMPLEMENTED** |
| Void issued CN | Forbidden (Conflict) | — | Hide action | **NOT_IMPLEMENTED** |
| CN as cash refund | Distinct semantics | — | Caption | N/A — do not conflate |
| Patient credit balance | `GET .../patients/{id}/credit-balance` | `billing.read` | Show | **SUPPORTED** |
| Clinic reconciliation HTTP | **MISSING** | — | Exclude (M8) | **NOT_IMPLEMENTED** |
| PDF render | **MISSING** | — | Exclude | **NOT_IMPLEMENTED** |

## Semantics (backend truth)

### Refund
- Linked to a **payment**; optional `invoice_id` scopes allocation reversal.
- Payment row is **never mutated**; refunds are separate immutable `issued` rows.
- Full or partial; amount must be ≤ `refundable_for_payment`.
- Reverses allocations first, then records refund.
- Audit: `refund.created`.

### Credit note
- Linked to exactly one **invoice**.
- Lifecycle: `draft → issued` or `draft → voided`. Issued is immutable.
- Cap: amount ≤ invoice outstanding at create and re-checked at issue.
- Reduces outstanding via derivation (`outstanding = total − allocated − credited`); **does not** return cash.
- Numbering allocated at issue (FY + doc_number).
- Audit: `credit_note.created` / `.issued` / `.voided`.

## Entity distinctions

| Concept | Meaning |
|---------|---------|
| Payment | Money received (manual/offline methods) |
| Allocation | Links payment → invoice |
| Refund | Money returned against a payment (clinic record) |
| Credit note | Formal invoice correction document |
| Patient credit | Sum of unallocated payment remainders |

## Existing tests

- `tests/api/test_billing_adjustments_api.py` — refund/CN flows, auth, IDOR, concurrency
- `tests/service/test_refunds_credits.py` — service semantics
