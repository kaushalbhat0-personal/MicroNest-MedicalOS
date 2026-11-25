# Test Evidence — M9

## Backend

```
pytest tests/api/test_staff.py -q
```

**Result:** 6 passed (exit 0). Covers directory/profile, invite list/revoke/accept, schedules, attendance, leave, and related RBAC paths in that module.

Related isolation remains covered by broader suites (`tests/isolation/`, tenants API) — not re-run as a blocking gate for this milestone beyond staff module green.

## Desktop

```
cd apps/desktop && npm run test:unit && npm run typecheck
```

**Result:** 21 Vitest passed (6 files); `tsc --noEmit` clean.

New unit coverage: `src/lib/staffApi.test.ts` (weekday / schedule index helpers).

## API evidence

`scripts/_p18_m9_workforce_evidence.py` → [evidence/m9_workforce_evidence.json](./evidence/m9_workforce_evidence.json)

Demonstrated synthetic flow (no tokens / no PII dumped):

1. Admin staff directory + profile  
2. Invitation create (token returned once; **not** stored in evidence)  
3. Invitation revoke  
4. Roles + practitioners + verification queue  
5. Staff schedule create + deactivate  
6. Attendance check-in / check-out / list  
7. Leave types + leave request create  
8. Leave self-decide → **403** (backend blocks)  
9. Leave cancel HTTP → **404** (**NOT IMPLEMENTED**)  
10. Cross-tenant staff access denied  

`pass: true`

## EXE

Debug binary: `apps/desktop/src-tauri/target/debug/healthcare-os-desktop.exe`  
`/staff` routes to `StaffHub`. Filmed multi-step UI click-through is **PARTIAL**; API evidence covers the backend-backed workflow steps with synthetic staff.
