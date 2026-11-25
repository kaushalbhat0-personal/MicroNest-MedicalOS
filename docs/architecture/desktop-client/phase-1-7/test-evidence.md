# Test Evidence — M8

## Backend

```
pytest tests/api/test_billing_estimates_api.py \
       tests/api/test_billing_invoices_api.py \
       tests/api/test_billing_payments_api.py \
       tests/service/test_estimates.py \
       tests/service/test_invoices.py \
       tests/service/test_payments.py \
       tests/service/test_outstanding_aggregate_reconcile.py -q
```

**Result:** 58 passed (exit 0).

## Desktop

```
cd apps/desktop && npm run test:unit && npm run typecheck && npm run build
```

**Result:** 19 Vitest passed; tsc 0; production build OK.

## API evidence

`scripts/_p17_m8_billing_evidence.py` → [evidence/m8_billing_evidence.json](./evidence/m8_billing_evidence.json)

Demonstrated synthetic flow:
1. Create estimate → issue  
2. Convert → draft invoice → issue (FY + doc_number)  
3. Record cash payment (idempotent replay)  
4. Allocate partial 200 of 500  
5. Balance outstanding 300  
6. Over-allocation rejected  
7. Cross-tenant blocked  
8. Patient overview outstanding matches  

`pass: true` — no tokens/PHI.

## EXE

Debug rebuild embeds BillingHub at `/billing/invoices`.
