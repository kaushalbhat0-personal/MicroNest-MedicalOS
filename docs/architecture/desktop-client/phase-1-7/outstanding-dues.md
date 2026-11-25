# Outstanding Dues

**Screen:** Billing hub → Outstanding dues  
**Route:** `/billing/invoices?tab=dues`

No dedicated AR aging API. Workspace loads invoices (bounded limit) and filters with `invoiceHasOutstanding` using backend `outstanding_amount`.

| Display | Source |
|---------|--------|
| Totals / paid / outstanding | Invoice response strings |
| Past due date hint | Informational only when `due_date` < today — not labeled “overdue” as a backend status |
| Navigate | Patient 360, invoice detail, collect payment |

Patient overview `outstanding_balance` used on Patient 360 header.
