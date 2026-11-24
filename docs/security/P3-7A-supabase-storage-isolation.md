# P3.7A — Supabase Storage Provider Isolation

**Date:** 2026-11-24  
**Endpoint:** real Supabase S3-compatible API (not local adapter)  
**Bucket:** `dental-os` (private)  
**Adapter:** `backend/app/platform/adapters/s3_storage.py` (`S3StorageAdapter`)  
**Objects:** synthetic UTF-8 payloads only; cleaned up after drill

## Verdict: **CONDITIONAL PASS** (provider + app-layer)

| Layer | Status |
|-------|--------|
| Private bucket / public URL denial | **PASS** |
| Presigned GET mint + fetch | **PASS** |
| Expired / tampered presigned URL | **PASS** |
| Path traversal rejected by adapter | **PASS** |
| Tenant-bound object key layout | **PASS** (`tenants/{tid}/encounters/{eid}/documents/{doc}`) |
| Per-tenant IAM / bucket policy isolation | **NOT PROVEN** — single S3 credential can read/write/delete any key in the bucket |

## Drill matrix

| # | Case | Result |
|---|------|--------|
| 1 | Upload tenant A object | PASS |
| 2 | Retrieve tenant A object | PASS |
| 3 | Distinct A/B object payloads | PASS |
| 4 | Delete with shared credential | **EXPECTED_ACCOUNT_SCOPE** (credential can delete any key) |
| 5 | Client path traversal key | PASS (adapter `ValueError`) |
| 6 | Mint signed URL | PASS |
| 7 | Unauthenticated public object URL | PASS (denied) |
| 8 | Expired signed URL | PASS |
| 9 | Tampered signed URL (key swap) | PASS |
| 10 | Tenant-bound paths | PASS |
| — | Authorized signed fetch of A | PASS |
| — | Cleanup synthetic keys | PASS |

## Credential scope

`S3_ACCESS_KEY` / `S3_SECRET_KEY` are **project Storage S3 credentials**, not restricted to a single object prefix. They are **not** the Supabase management PAT (`SUPABASE_ACCESS_TOKEN`).

**Implication:** Cross-tenant isolation at the provider depends on:

1. Server-derived keys (P3.6) — **PASS** in application.  
2. API authorization before minting signed URLs — **PASS** (P3.6).  
3. Optional future hardening: separate buckets or IAM prefix policies per tenant (not available as fine-grained with current shared key).

Do **not** mark “shared production object-storage tenant IAM isolation” as PASS.

## Application contract (unchanged)

| Setting name (app) | Staging source |
|--------------------|----------------|
| `STORAGE_ADAPTER` | `s3` (on Render; local remains local) |
| `S3_ENDPOINT_URL` | Supabase Storage S3 endpoint |
| `S3_BUCKET` | `dental-os` |
| `S3_REGION` | `eu-west-3` |
| `S3_ACCESS_KEY` | Storage access key |
| `S3_SECRET_KEY` | Storage secret key |

Frontend must never receive these variables (`NEXT_PUBLIC_*` forbidden for S3 secrets).

## P3.6 continuity

Server-allocated `storage_key` and consent hard-gate remain in code. This drill did not regress those controls; it proves the **provider path** works with tenant-prefixed keys and private access.
