# P3.6 — Threat Model (Synthetic Data Security Verification)

**Date:** 2026-11-24  
**Scope:** Document object binding, dental consent hard-gate, multi-tenant isolation.  
**Data:** Synthetic fixtures only. No real PHI.

## Assets

| Asset | Sensitivity |
|-------|-------------|
| Document metadata + storage object bytes (images/reports) | High (clinical) |
| Dental procedure records + consent decisions | High (clinical/legal) |
| Patient demographics, encounters, notes, Rx, billing | High |
| Portal enrollments / session tokens | High |
| Tenant membership & roles | Medium–High |

## Actors

- Authenticated clinic staff (owner, dentist/doctor, receptionist/staff)
- Patient portal identity (self-scoped)
- Cross-tenant attacker (compromised or malicious staff of Tenant B)
- Unauthenticated internet client

## Threats and controls

| Threat | Attack path | Control | P3.6 status |
|--------|-------------|---------|-------------|
| Horizontal privilege escalation | Role without `dental.*` / `patient.*` calls APIs | `require(P.*)`; deny-by-default | **PASS** (staff → 403 on doc upload/access) |
| Cross-tenant access | Substitute Tenant A IDs under Tenant B session | `match_tenant` + service tenant checks + RLS | **PASS** (404 no-oracle) |
| IDOR (document) | Guess/swap `document_id` across tenants | `grant_document_access` tenant + encounter scope | **PASS** |
| IDOR (patient) | Search/get foreign patient UUID | Tenant-scoped list/get + RLS | **PASS** (API spot + existing isolation suite) |
| Client-controlled storage paths | POST document with foreign/`../` `storage_key` | Server allocates `tenants/{tid}/encounters/{eid}/documents/{doc_id}`; reject traversal | **PASS** (remediated) |
| Signed URL leakage / forgery | Mint URL without auth; reuse expired; key mismatch | Authz before mint; 300s TTL; HMAC verify binds key | **PASS** (local adapter); production S3 see gaps |
| Consent bypass | Advance procedure without / with withdrawn / wrong-subject consent | Server hard-gate on `in_progress`/`completed` | **PASS** (procedure-record gate); plan-activation still open |
| Stale tenant context | Change `X-Tenant` between authorize and retrieve | Per-request `match_tenant` + membership | **PASS** |
| Unauthorized upload | Staff without `dental.record` | Permission gate | **PASS** |
| Unauthorized deletion | DELETE document | No delete API | **NOT APPLICABLE** |
| Shared bucket object theft | Client key points at other tenant object | Server-derived keys + access binds DB key to tenant prefix | **PASS** (API/local); **BLOCKED** for shared prod S3 isolation proof |
| Frontend-only consent | UI hides button; API still called | Gate in `transition_procedure_record` | **PASS** |

## Trust boundaries

1. Browser / mobile client → API (untrusted input, including `storage_key` hint).  
2. API → PostgreSQL app role (RLS `app.tenant_id`).  
3. API → StoragePort (local or S3); keys must be server-owned.  
4. Clinical policy → consent gate (product rule for procedure lifecycle; plan activation deferred).

## Residual risks

- Production shared-object-storage isolation not proven against a real S3 account in this phase.  
- Consent expiry not modeled (no expiry column) — **NOT APPLICABLE**.  
- Plan-level consent hard-gate not established by dental ADR — decision required.  
- Local HMAC tokens are not HTTP URLs; provider-level ACL evidence remains separate.
