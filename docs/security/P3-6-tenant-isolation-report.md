# P3.6 — Tenant Isolation Report

**Date:** 2026-11-24  
**Database:** `healthcare_os_test` (serial pytest)  
**Fixtures:** Synthetic Tenant A / Tenant B (fictional names/emails `@example.com`)

## Methods

1. **API-level:** authenticated doctor clients with `X-Tenant`; cross-tenant ID substitution.  
2. **Database-level:** app-role session with `set_config('app.tenant_id', …)` raw SQL against `document_references`.  
3. **Regression:** existing `tests/isolation/*` and `tests/portal/*` suites.

## Coverage

| Area | Status | Notes |
|------|--------|-------|
| Patient registration / search | **PASS** | Cross-tenant search does not return A; IDOR 403/404 |
| Patient 360 / timeline | **PASS** | Covered by existing clinical isolation suite (regression) |
| Clinical notes / diagnoses | **PASS** | Existing `test_clinical_isolation.py` |
| Prescriptions | **PASS** | Existing clinical isolation + Rx service tests |
| Treatment plans | **PASS** | Dental API + isolation |
| Estimates / invoices | **PASS** | Existing billing isolation (prior P3.0) |
| Appointments | **PASS** | `test_scheduling_isolation.py` |
| Follow-ups / communication logs | **PASS** | Isolation + portal/comms prior evidence |
| Inventory | **PASS** | Prior isolation coverage |
| Staff records | **PASS** | Prior staff/tenancy tests |
| Patient portal enrollment / access | **PASS** | `tests/portal/*`, `test_portal_link_rls.py` |
| Tenant switching / stale context | **PASS** | Document access with switched `X-Tenant` |
| RLS under app role | **PASS** | `test_p36_rls_blocks_cross_tenant_document_select` + `test_rls.py` |
| Document references | **PASS** | P3.6 security suite |

## Classifications

| Control | Status |
|---------|--------|
| Local API authorization isolation | **PASS** |
| PostgreSQL / RLS isolation | **PASS** |
| Actual object-storage provider isolation | **BLOCKED** (local adapter only) |
| Production infrastructure verification | **BLOCKED** |

## Skips

None in the P3.6 security module. Broader monorepo skips (if any) are listed in the remediation / PHI gate reports from the regression run.
