# Estimate Workspace

**Screen:** Billing hub → Estimates tab (`BillingHub`)  
**Route:** `/billing/invoices?tab=estimates`

| Feature | API | Permission | Financial rule | Tests |
|---------|-----|------------|----------------|-------|
| List/filter | GET `/estimates` | `billing.read` | Backend totals as strings | estimates API + desktop unit helpers |
| Detail | GET `/estimates/{id}` | `billing.read` | Display subtotal/tax/grand_total only | evidence |
| Issue | POST `.../issue` | `billing.create` | draft→issued; ConfirmDialog | evidence |
| Cancel/Expire | POST cancel/expire | `billing.create` | Transition map | estimates API |
| Convert | POST `.../convert` | `billing.create` | issued/converted; creates **draft** invoice; idempotency key | evidence convert + replay |

Does **not** auto-issue estimates from treatment plans. Frontend never invents totals.
