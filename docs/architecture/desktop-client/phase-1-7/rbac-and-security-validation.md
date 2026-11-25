# RBAC and Security — M8

| Capability | Permission |
|------------|------------|
| Billing nav / hub | `billing.read` |
| Estimate issue/convert/cancel | `billing.create` |
| Invoice issue/void | `invoice.issue` |
| Payment + allocate | `payment.record` |
| Refunds/credit notes | `billing.refund` (API exists; not primary M8 UI) |

## Controls

- Totals never computed as source of truth in UI
- Idempotency keys on pay/allocate/convert
- Cross-tenant invoice access blocked (evidence)
- Billing UI state cleared with patient/encounter on workspace switch
- No PHI/payment secrets in evidence JSON
- Patient 360 billing gated by `billing.read`
