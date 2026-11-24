# P3.6 — PHI Release Gate

**Date:** 2026-11-24  
**Gate question:** May real patient data be onboarded?

## Final verdict: **CONDITIONAL PASS**

Local synthetic-data API authorization, PostgreSQL/RLS isolation, server-derived document keys, and procedure-record consent hard-gating are verified.  
**Real patient data remains BLOCKED** until external/clinical gaps below are closed.  
**Synthetic staging may proceed.**

Do **not** claim production PHI readiness from local tests alone.

## Layer scorecard

| Layer | Verdict | Notes |
|-------|---------|-------|
| Local API authorization | **PASS** | Document access, consent gate, IDOR/cross-tenant fail-closed |
| PostgreSQL / RLS isolation | **PASS** | App-role raw SQL + isolation suites |
| Actual object-storage provider isolation | **BLOCKED** | Only `LocalStorageAdapter` exercised; shared S3 not proven |
| Clinical consent-policy validation | **CONDITIONAL** | Procedure hard-gate implemented; plan-level / exemptions / expiry need dental sign-off |
| Production infrastructure verification | **BLOCKED** | Out of P3.6 scope |

## P3.0 blockers — disposition

| P3.0 blocker | Disposition |
|--------------|-------------|
| Client-supplied document `storage_key` | **Remediated + PASS** (local) |
| Shared object-storage tenant isolation | **Still BLOCKED** for production provider proof |
| Dental consent hard-gate | **Remediated for procedure in_progress/completed** — plan-level **BLOCKED** pending clinical decision |

## Synthetic staging

| Action | Allowed? |
|--------|----------|
| Synthetic multi-tenant staging / pilot rehearsal | **Yes** |
| Real-patient onboarding / PHI import | **No** |
| Shared production S3 with PHI objects | **No** until provider isolation drill |

## Evidence package

| Document | Path |
|----------|------|
| Threat model | `docs/security/P3-6-threat-model.md` |
| Document isolation | `docs/security/P3-6-document-isolation-report.md` |
| Dental consent | `docs/security/P3-6-dental-consent-report.md` |
| Tenant isolation | `docs/security/P3-6-tenant-isolation-report.md` |
| Remediation | `docs/security/P3-6-remediation-report.md` |

## Regression results (2026-11-24, serial on `healthcare_os_test`)

| Suite | Result | Skips |
|-------|--------|-------|
| `tests/security/test_p36_document_consent_isolation.py` | Green | None |
| `tests/api/test_document_access_api.py` | Green | None |
| `tests/api/test_dental_api.py` + `tests/service/test_rx_dental.py` | Green | None |
| `tests/isolation` + `tests/portal` + document access + security | Green (~93) | None observed |
| Backend ruff on remediated dental modules | Green | — |
| Web / UI typecheck | Green | — |
| UI unit tests | 24 pass / 0 fail / 0 skipped | None |
| Web production build | Succeeded | — |

## Remaining security blockers (before real PHI)

1. Prove shared production object-storage isolation (tenant prefix IAM / bucket policy / signed URL ACLs) against the real provider.  
2. Obtain qualified dental professional decisions on plan-level consent, procedure exemptions, and consent expiry.  
3. Production infrastructure verification (env secrets, WAF, backup/restore, pen-test) per P7/P8.

## Recommended next phase

**P3.7 — Production storage isolation drill + clinical consent policy sign-off**  
- Stage a dedicated non-PHI S3 (or equivalent) bucket; verify cross-tenant key denial at provider layer.  
- Capture dental professional answers in an ADR amendment to P3-02.  
- Only then reopen the real-PHI onboarding gate.
