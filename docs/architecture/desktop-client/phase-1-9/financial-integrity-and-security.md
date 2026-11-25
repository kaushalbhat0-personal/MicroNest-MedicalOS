# Financial Integrity and Security — M10

## Authorization

| Operation | Permission |
|-----------|------------|
| Read refunds / credit notes / balances | `billing.read` |
| Create refund, create/issue/void CN | `billing.refund` |

Backend `require()` enforces every mutation. Desktop hides actions without `billing.refund` but does not treat UI as authorization.

## Tenant isolation

- All calls use authenticated desktop client + `X-Tenant` from workspace
- Cross-tenant refund GET → denied (evidence)
- Location scope follows payment/invoice location membership on backend

## Financial precision

- Amounts are backend decimal strings end-to-end
- Client form guards use integer cents helpers (`parseMoneyToCents`) — never authoritative
- No floating-point for settlement truth
- Currency displayed explicitly (INR from payment/invoice)

## Idempotency

- Refund and credit-note create accept `idempotency_key` in body
- Desktop generates one key per confirm open and reuses on submit
- Evidence: identical replay returns same refund id

## Audit

Backend appends `refund.created`, `credit_note.created` / `.issued` / `.voided`.

## Secrets / PHI

- No payment credentials in desktop
- Evidence files omit tokens, patient names, and invite secrets
- Refund caption clarifies no gateway settlement
