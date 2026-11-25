# Test Evidence — M11

## Backend

```
pytest tests/api/test_dental_api.py \
       tests/security/test_p36_document_consent_isolation.py \
       tests/service/test_rx_dental.py -q
```

**Result:** 42 passed (exit 0). Includes finding lifecycle, plan/consent, procedure consent gate, document access isolation, dental Rx service.

## Desktop

```
cd apps/desktop && npm run test:unit && npm run typecheck && npm run build
```

**Result:** 32 Vitest passed (7 files); `tsc` clean; Vite production build OK.

New: `src/lib/dentalApi.test.ts` — FDI, surfaces, odontogram precedence, consent transition helpers.

## API evidence

`scripts/_p110_m11_dental_evidence.py` → [evidence/m11_dental_evidence.json](./evidence/m11_dental_evidence.json)

Demonstrated (synthetic, no PHI/tokens):

1. Invalid tooth + primary dentition rejected  
2. Finding record/list/resolve with surfaces  
3. Plan create + activate without plan consent  
4. Procedure in_progress without consent → **403**  
5. Consent grant → in_progress allowed  
6. Cross-tenant dental denied  

`pass: true` · `dentist_validation: PENDING`

## EXE

```
cd apps/desktop && npx tauri build --debug
```

**Result:** debug EXE rebuilt (`healthcare-os-desktop.exe`, ~18 MB) embedding Dental tab + TreatmentPlansHub. Filmed UI click-through **PARTIAL**.
