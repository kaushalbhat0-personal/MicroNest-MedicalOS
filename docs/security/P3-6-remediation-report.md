# P3.6 — Remediation Report

**Date:** 2026-11-24  
**Git:** No commit/push (working tree preserved per constraints).  
**HEAD baseline noted by request:** `2a0974e41af9e334e147794f45e258f34d6814d3`

## Vulnerabilities reproduced

1. **Client-supplied `storage_key` on document create** — attacker could persist an arbitrary object path (including another tenant prefix or path traversal) as the document’s storage key. Signed-URL minting then trusted the DB row.  
2. **Dental procedure consent not hard-gated** — `transition_procedure_record` to `in_progress`/`completed` succeeded with no granted consent.

## Fixes applied

### 1. Server-derived document storage keys

**Files:** `backend/app/modules/dental/plans.py`, `backend/app/modules/dental/schemas.py`

- `allocate_document_storage_key(...)` → `tenants/{tenant_id}/encounters/{encounter_id}/documents/{document_id}`
- `create_document_ref` always assigns the server key; client hint ignored for selection
- Malformed hints (`..`, absolute, `\`, NUL) → `ValidationError` (422)
- `grant_document_access` calls `_assert_document_storage_bound` (tenant prefix required)

### 2. Procedure consent hard-gate

**File:** `backend/app/modules/dental/plans.py`

- Before transition to `in_progress` or `completed`, require a `Consent` row with `procedure_record_id`, `tenant_id`, `status=granted`
- Missing / pending / declined / withdrawn → `ForbiddenError` (403)
- `cancelled` remains ungated
- Plan activation not gated (clinical decision pending)

## Regression tests added/updated

| File | Role |
|------|------|
| `tests/security/test_p36_document_consent_isolation.py` | New synthetic A/B isolation + consent + storage suite |
| `tests/api/test_document_access_api.py` | Assert server-allocated keys |
| `tests/api/test_dental_api.py` | Lifecycle expects consent before status advances |
| `tests/service/test_rx_dental.py` | Service lifecycle + document key validation |

## What was not changed

- SaaS payment / Razorpay code paths  
- RLS policies (not weakened)  
- No Docker; no destructive DB ops beyond normal test TRUNCATE harness  
- No real patient data  
- No commit

## Evidence gaps remaining

| Gap | Status |
|-----|--------|
| Shared production S3 prefix/IAM isolation drill | Open |
| Dental professional sign-off on plan-level consent & exemptions | Open |
| Full production infrastructure / WAF / pen-test | Out of scope (P7/P8) |
