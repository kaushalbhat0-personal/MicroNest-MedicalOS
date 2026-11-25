# Invoice Workspace

**Screen:** Billing hub → Invoices tab  
**Route:** `/billing/invoices?tab=invoices`

| Feature | API | Permission | Financial rule | Tests |
|---------|-----|------------|----------------|-------|
| List | GET `/invoices` | `billing.read` | Shows allocated + outstanding | invoices API |
| Detail | GET `/invoices/{id}` | `billing.read` | FY + doc_number after issue | evidence |
| Balance | GET `.../balance` | `billing.read` | Authoritative after pay | evidence |
| Issue | POST `.../issue` | `invoice.issue` | Numbering lock | evidence |
| Void | POST `.../void` | `invoice.issue` | Reason; no settlement | invoices API |

Convert flow lands on draft invoice → Issue required for numbered document.
