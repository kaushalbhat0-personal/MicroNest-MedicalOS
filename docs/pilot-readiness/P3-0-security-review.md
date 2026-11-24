# P3.0 — Security & Tenant Isolation Review

**Verdict for controlled pilot:** **OK with documented Risks** — no isolation Blocker found for synthetic two-tenant pilots when object storage is local/dev-scoped.

## Classification table

| Control | Verdict | Evidence |
|---------|---------|----------|
| Tenant isolation / RLS | OK | `deps.py` `app.tenant_id`; `tests/isolation/test_rls.py`, `test_tenant_isolation.py` |
| Location scoping | OK | Clinical/inventory/scheduling scope checks; `test_clinical_isolation.py` |
| Server-derived identity | OK | Portal patient from `portal_links`; `X-Tenant` is membership selector only |
| Role authorization | OK | `require(P.*)`; `test_permissions.py` |
| Portal isolation | OK | `test_portal_security.py`, `test_portal_link_rls.py` |
| Document signed URLs | OK | 300s TTL; client cannot set key/expiry (`test_document_access_api.py`) |
| Patient vs internal | OK | Drafts hidden from portal |
| Audit logging | OK | Hash chain; refs-only payloads |
| Consent (comms) | OK | WhatsApp link gated |
| Consent (dental procedure hard-stop) | Risk | Workflow exists; no hard block before procedure |
| File upload model | Risk | Client-supplied `storage_key` on document create — Blocker if shared prod bucket without prefix binding |
| Signup / workspace ownership | Risk | Unverified users may provision; ownership from session OK |
| Inactive tenant | OK | `tenants.status` gates; commercial delinquency ≠ abuse suspend |
| Invitation expiry | OK | `test_staff.py` |
| API validation | OK | OpenAPI + 422 suites |
| Secrets in logs / frontend | OK | Scrubbing; no tokens in storage |

## Pilot blockers (security)

None for **synthetic / local-storage** pilots.

**Would become Blocker before production PHI:**

1. Shared S3 without server-issued tenant-prefixed keys.  
2. Weakening RLS or portal 404-oracle for demos.

## SaaS payments

Out of pilot clinical scope. P2.5 remains frozen. Do not use live Razorpay credentials for clinic pilots.

## Test evidence (serial runs, 2026-11-24)

| Suite | Result |
|-------|--------|
| Isolation (tenant, RLS, clinical, scheduling, portal_link) + portal security/flows | **Green** when run alone (43 passed earlier serial run) |
| Parallel pytest on shared `healthcare_os_test` | **Unsafe** — schema/seed races; always serial |
| Document access | Covered by `test_document_access_api.py` (not re-run in final batch; prior green in repo) |

## UX security-adjacent notes

- Permission-filtered nav (`apps/web/lib/nav.ts`) is good.  
- Many staff pages lack explicit 403 empty states (Risk: confused ops, not auth bypass).  
- “Plans” nav label collides with treatment plans vs SaaS catalog.
