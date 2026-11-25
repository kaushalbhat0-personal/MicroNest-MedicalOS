# Test Evidence — Phase 1.4+1.5

## Backend (PostgreSQL)

```
pytest tests/api/test_patients_api.py \
       tests/api/test_patient_360.py \
       tests/api/test_appointments_api.py \
       tests/api/test_reception_queue.py \
       tests/isolation/test_scheduling_isolation.py -q
```

**Result:** 31 passed (exit 0) on 2026-11-25.

## Desktop unit

```
cd apps/desktop && npm run test:unit && npm run typecheck && npm run build
```

**Result:** 13 Vitest passed; `tsc` exit 0; Vite production build OK (`index-B5tyMbKg.js`).

## API runtime evidence (synthetic)

Script: `scripts/_p145_m5m6_api_evidence.py`  
Prerequisite: approved practitioner via `scripts/_p145_seed_verified_practitioner.py`  
Artifact: [evidence/m5m6_api_evidence.json](./evidence/m5m6_api_evidence.json)

| Check | Result |
|-------|--------|
| healthz | true |
| native login/logout | true |
| patients list/create/overview/timeline/patch | true |
| soft duplicate hint | true (count≥1) |
| availability endpoint | true (0 slots ok) |
| appointment create | true (200) |
| walk-in → checked_in | true |
| check-in + queue token | true |
| duplicate check-in | 200 (idempotent) |
| reception queue | true |
| cross-tenant blocked | true |
| **pass** | **true** |
| PHI/tokens in file | false |

## Desktop EXE

Rebuilt debug binary:

`apps/desktop/src-tauri/target/debug/healthcare-os-desktop.exe`

NSIS: `apps/desktop/src-tauri/target/debug/bundle/nsis/Healthcare OS_0.1.0_x64-setup.exe`

Interactive M3 auth remains valid from Phase 1.3. M5/M6 UI is embedded in this rebuild; full click-through tour was not separately recorded as a second evidence JSON (API contracts exercised above).

## Notes

- Synthetic data only (`desktop.poc@example.com`, PoC patients).
- Unverified practitioners on the tenant correctly return **403** on book until `set_verification(... approved)`.
