# Patient 360 — Billing Integration (M10)

## Screen

`PatientProfile` → **Billing** tab

## Permissions

Requires `billing.read`. Mutation deep-links still enforce `billing.refund` in BillingHub.

## Added content

| Card | Source |
|------|--------|
| Refunds | `listPaymentRefunds` per listed payment (soft-fail) |
| Credit notes | `listInvoiceCreditNotes` per listed invoice (soft-fail) |

Deep links:
- Open refunds → `/billing?patient=…&tab=refunds`
- Open credit notes → `/billing?patient=…&tab=credits`

## Rules

- No extra PHI beyond existing billing summary
- Totals remain backend strings via `MoneyDisplay`
- Caption: refund returns money against a payment; credit note corrects invoice outstanding
- N+1 bounded by existing payment/invoice list limits (≤50)
