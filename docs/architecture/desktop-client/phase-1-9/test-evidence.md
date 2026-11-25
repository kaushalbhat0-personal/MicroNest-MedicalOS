# Test Evidence — M10

## Backend

```
pytest tests/api/test_billing_adjustments_api.py \
       tests/service/test_refunds_credits.py -q
```

**Result:** 19 passed (exit 0). Covers refund/credit flows, over-refund, idempotency, auth matrix, IDOR, and service semantics.

## Desktop

```
cd apps/desktop && npm run test:unit && npm run typecheck && npm run build
```

**Result:** 25 Vitest passed; `tsc` clean; Vite production build OK (`index-Ds3SUHam.js`).

New/extended: `billingApi.test.ts` — refundable cents math, reason/amount guards, credit-note state helpers.

## API evidence

`scripts/_p19_m10_refunds_evidence.py` → [evidence/m10_refunds_evidence.json](./evidence/m10_refunds_evidence.json)

Demonstrated (synthetic, no tokens/PHI):

1. Invoice + payment + allocation  
2. Partial refund `100.00`  
3. Idempotent refund replay (same id)  
4. Over-refund rejected  
5. Refund list  
6. Credit-note draft → issue (doc_number assigned)  
7. Void issued CN rejected  
8. Void draft CN OK  
9. Outstanding after CN = `250.00` (300 − 50)  
10. Cross-tenant refund access denied  

`pass: true`

## EXE

```
cd apps/desktop && npx tauri build --debug
```

**Result:** exit 0.  
- Debug EXE: `apps/desktop/src-tauri/target/debug/healthcare-os-desktop.exe` (~18 MB)  
- NSIS: `apps/desktop/src-tauri/target/debug/bundle/nsis/Healthcare OS_0.1.0_x64-setup.exe` (~3.65 MiB)  

Embeds BillingHub tabs `refunds` / `credits`. Filmed multi-step UI click-through is **PARTIAL**; API evidence covers financial mutations.
