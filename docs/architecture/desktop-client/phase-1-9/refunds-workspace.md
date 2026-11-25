# Refunds Workspace

## Screen

`BillingHub` → **Refunds** tab (`?tab=refunds`)  
Component: `apps/desktop/src/components/billing/RefundsPanel.tsx`

## Scope

Patient-scoped only (no tenant-wide refund list API). Select a patient filter, then a payment.

## API

| Action | Endpoint | Permission |
|--------|----------|------------|
| List payments | `GET .../payments?patient_id=` | `billing.read` |
| List refunds | `GET .../payments/{id}/refunds` | `billing.read` |
| Create refund | `POST .../payments/{id}/refunds` | `billing.refund` |
| Get refund | `GET .../refunds/{id}` | `billing.read` |

## UX

- Refundable display hint: `refundableFromPayment` = allocated + unallocated (backend-derived fields; equals amount − refunded)
- Create form: amount, reason (2–200), optional invoice link from allocations
- ConfirmDialog shows amount, currency, payment, reason before submit
- Idempotency key generated once per confirm open; reused on submit; cleared after success/dismiss
- Busy flag prevents double-submit
- Caption: clinic record ≠ bank/gateway settlement
- Over-refund and other failures show backend error text; never marked success

## State

Refunds are created as `issued` and are immutable. No void UI (**NOT IMPLEMENTED**).

## Tests

- Backend: `test_billing_adjustments_api.py`, `test_refunds_credits.py`
- Desktop: `billingApi.test.ts` helpers; panel wired in BillingHub
- Evidence: partial refund, idempotent replay, over-refund rejected
