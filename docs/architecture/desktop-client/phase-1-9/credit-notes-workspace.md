# Credit Notes Workspace

## Screen

`BillingHub` → **Credit notes** tab (`?tab=credits`)  
Component: `apps/desktop/src/components/billing/CreditNotesPanel.tsx`

## Scope

Patient-scoped invoice selection (no tenant-wide CN list API).

## API

| Action | Endpoint | Permission |
|--------|----------|------------|
| Create draft | `POST .../invoices/{id}/credit-notes` | `billing.refund` |
| Issue | `POST .../credit-notes/{id}/issue` | `billing.refund` |
| Void draft | `POST .../credit-notes/{id}/void` | `billing.refund` |
| List for invoice | `GET .../invoices/{id}/credit-notes` | `billing.read` |
| Get | `GET .../credit-notes/{id}` | `billing.read` |
| Patient credit | `GET .../patients/{id}/credit-balance` | `billing.read` |

## UX

- Outstanding shown from invoice balance API
- Create draft with amount + reason; ConfirmDialog; idempotency key
- Issue draft → allocates FY + doc_number
- Void **draft only**; issued void action hidden / rejected by backend
- Caption: credit note ≠ cash refund; outstanding reduced via backend derivation
- Patient unallocated credit balance displayed when patient selected

## State transitions

`draft` → `issued` | `voided`  
`issued` / `voided` terminal

## Tests

- Backend adjustments + service suites
- Desktop helpers `canCreateCreditNote` / `canIssueCreditNote` / `canVoidCreditNote`
- Evidence: draft → issue, void issued rejected, void draft OK, outstanding after CN
