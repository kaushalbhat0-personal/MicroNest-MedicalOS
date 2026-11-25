# Test Evidence — Phase 1.6 / M7

## Backend regression

```
pytest tests/api/test_clinical_api.py \
       tests/service/test_clinical.py \
       tests/isolation/test_clinical_isolation.py \
       tests/service/test_rx_dental.py \
       tests/api/test_dental_api.py \
       tests/api/test_followups_comms.py \
       tests/api/test_patient_360.py -q
```

**Result:** 58 passed (exit 0).

## Desktop

```
cd apps/desktop && npm run test:unit && npm run typecheck && npm run build
```

**Result:** 15 Vitest passed; tsc 0; Vite production build OK.

## API clinical evidence (synthetic)

Scripts:

- `scripts/_p16_seed_linked_practitioner.py` (user↔practitioner link)
- `scripts/_p16_m7_clinical_evidence.py`

Artifact: [evidence/m7_clinical_evidence.json](./evidence/m7_clinical_evidence.json)

| Check | Result |
|-------|--------|
| encounter open/close | true |
| note create + finalize | true |
| diagnosis create | true |
| rx create + sign | true |
| vitals create | true |
| plan draft create (+ cancel for close) | true |
| follow-up create | true |
| timeline has encounter events | true |
| cross-tenant blocked | true |
| **pass** | **true** |
| PHI/tokens | false |

## EXE

Debug rebuild embeds M7 UI:

`apps/desktop/src-tauri/target/debug/healthcare-os-desktop.exe`

Prerequisite for clinician writes: signed-in user must have an **approved linked practitioner** (seed helper above).
