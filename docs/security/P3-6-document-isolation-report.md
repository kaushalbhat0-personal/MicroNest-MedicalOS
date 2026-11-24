# P3.6 — Document Isolation Report

**Date:** 2026-11-24  
**Verdict (local API + local storage adapter):** **PASS** after remediation  
**Verdict (shared production object-storage provider isolation):** **BLOCKED** — not tested against real S3

## Pre-fix finding (reproduced)

`POST .../encounters/{id}/documents` accepted client `storage_key` and persisted it verbatim (`create_document_ref`). Access minting correctly resolved the key from the DB row, so a crafted create could bind a document reference to another tenant’s object path in a shared bucket.

## Remediation

| Change | Location |
|--------|----------|
| Server allocates `tenants/{tenant_id}/encounters/{encounter_id}/documents/{document_id}` | `plans.allocate_document_storage_key` / `create_document_ref` |
| Client `storage_key` optional/deprecated; ignored for selection | `DocumentRefCreateRequest`, `create_document_ref` |
| Path traversal / absolute / null / backslash hints → 422 | `_assert_storage_key_safe` |
| Access rejects non-tenant-prefixed / poisoned legacy keys | `_assert_document_storage_bound` in `grant_document_access` |

API compatibility: clients may still send `storage_key`; it does not select storage. Response returns the server key.

## Test matrix

| # | Case | Result | Evidence |
|---|------|--------|----------|
| 1 | Authorized retrieval of own document | **PASS** | `test_p36_authorized_retrieval_uses_server_key`, `test_document_access_api` |
| 2 | Cross-tenant document ID | **PASS** | 404; `test_p36_cross_tenant_document_id_is_404` |
| 3 | Cross-patient (same tenant, provider read model) | **PASS** | Explicitly allowed; documented |
| 4 | Cross-encounter list substitution | **PASS** | Empty list for other encounter |
| 5 | Client-supplied storage_key manipulation | **PASS** | Foreign key ignored |
| 6 | Path traversal / malformed refs | **PASS** | 422 |
| 7 | Unauthorized upload | **PASS** | staff → 403 |
| 8 | Unauthorized deletion | **NOT APPLICABLE** | No delete endpoint (405/404) |
| 9 | Expired signed capability | **PASS** | Local adapter `verify_signed_access` after TTL |
| 10 | Signed capability for wrong key/tenant | **PASS** | Key mismatch fails verify; cross-tenant access 404 |
| 11 | Missing document permission | **PASS** | staff → 403 on access |
| 12 | Stale tenant header | **PASS** | 403/404 |

## Storage evidence distinction

| Layer | Proven in P3.6? |
|-------|-----------------|
| Database/API authorization + server-derived keys | **Yes** |
| Local `LocalStorageAdapter` HMAC expiry / key bind | **Yes** |
| Real S3 bucket IAM / prefix isolation / KMS | **No — BLOCKED** |

Do **not** treat this report as production object-storage isolation PASS.
