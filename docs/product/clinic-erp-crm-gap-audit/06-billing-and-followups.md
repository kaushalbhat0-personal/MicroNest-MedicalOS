# 06 — Billing and follow-ups

## Billing (P4)

| Capability | Classification | Evidence |
|------------|----------------|----------|
| Catalog / estimates / invoices | **IMPLEMENTED AND VERIFIED** | `modules/billing/*`, `tests/api/test_billing_*` |
| Partial payments / allocations | **IMPLEMENTED AND VERIFIED** | `payments.py` + API tests |
| Outstanding balances | **IMPLEMENTED AND VERIFIED** | Server-derived `outstanding_amount` |
| Receipts / refunds / credit notes | **IMPLEMENTED AND VERIFIED** | Dedicated modules + tests |
| Line discounts | **IMPLEMENTED AND VERIFIED** | P4-01: line-level only |
| Patient credit | **IMPLEMENTED AND VERIFIED** | `…/credit-balance` |
| Unified patient billing timeline | **PARTIALLY IMPLEMENTED** | Parallel tables on profile |
| Multi-location reports | **PARTIALLY IMPLEMENTED** | `location_id` + numbering; no reports API |
| Financial reports / CSV export | **MISSING** | `modules/reports` stub |
| PDF render | **OUT OF SCOPE** | P4-01 seam only |
| Portal billing read | **IMPLEMENTED AND VERIFIED** | Portal projections + tests |

**Reuse rule:** do not duplicate billing tables or client-side money math.

## Follow-ups / communications

| Capability | Classification | Evidence |
|------------|----------------|----------|
| Dental recalls | **IMPLEMENTED AND VERIFIED** | `recalls` model + API + UI + portal list |
| Generic CRM follow-ups | **MISSING** | — |
| Missed-appointment follow-up workflow | **MISSING** | `no_show` exists; no linked workflow |
| Payment reminders | **MISSING** | — |
| Manual communication log | **MISSING** | — |
| WhatsApp Web click-to-chat | **IMPLEMENTED BUT NEEDS IMPROVEMENT** (post-slice) | User-initiated `wa.me` link on patient profile when phone present; automation still denied in `eligibility.py` |
| Automated WhatsApp | **OUT OF SCOPE** | Product rule this phase |
| Notification consent store | **MISSING** | Constants in `eligibility.py` only |
| Appointment confirmation enqueue | **PARTIALLY IMPLEMENTED** | Outbox request on create if phone present; adapters non-prod |
