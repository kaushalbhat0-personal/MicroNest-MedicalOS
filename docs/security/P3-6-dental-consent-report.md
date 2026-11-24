# P3.6 — Dental Consent Report

**Date:** 2026-11-24  
**Data:** Synthetic consenter names only.

## Product requirements (established)

From `docs/decisions/P3-02-dental-model.md`:

- Consent binds to exactly one subject: **plan XOR procedure record**.  
- Lifecycle: `pending → granted|declined`; `withdrawn` from `granted` only.  
- ADR does **not** define which transitions are clinically mandatory.

From P3.0 / pilot readiness (PHI release prerequisite):

- Dental consent must **hard-gate** before procedure advancement (clinical safety Risk → Blocker for real PHI).

## Policy implemented in P3.6 (explicit)

| Operation | Consent required? | Enforcement |
|-----------|-------------------|-------------|
| Create procedure record (`planned`) | No | Recording only |
| Transition → `in_progress` | **Yes — granted consent on that procedure_record** | `ForbiddenError` / HTTP 403 |
| Transition → `completed` | **Yes — granted consent still present** | Same (re-checked) |
| Transition → `cancelled` | No | Allowed without consent |
| Plan activate / complete | **Not gated** | See decision required |

Rationale: implements the P3.0 pilot safety gate without inventing broader dental law. Scope is procedure-record lifecycle only.

## Decision required (qualified dental professional)

1. Must **plan activation** require a granted plan-scoped consent?  
2. Are any procedure catalog codes exempt (e.g. exam-only)?  
3. Should consent **expire** after N days? (no column today → **NOT APPLICABLE** for expiry tests)  
4. Is withdrawn-after-`in_progress` allowed to block `completed` (current: **yes, fail-closed**)? Confirm clinically.

Until (1)–(3) are answered, do not claim full clinical-policy validation.

## Test matrix

| Case | Result | Evidence |
|------|--------|----------|
| Valid granted consent → in_progress/completed | **PASS** | API + service lifecycle tests |
| Missing consent | **PASS** | 403 / `ForbiddenError` |
| Withdrawn consent blocks completed | **PASS** | `test_p36_procedure_requires_granted_consent` |
| Expired consent | **NOT APPLICABLE** | No expiry model |
| Wrong procedure consent | **PASS** | Consent on record A does not unlock B |
| Wrong tenant consent subject | **PASS** | Cross-tenant create consent → 404 |
| Pending / declined | **PASS** | Fail-closed |
| Concurrent withdraw before completed | **PASS** | Re-check at each gated transition |
| Frontend manipulation / direct API | **PASS** | Gate is server-side in `transition_procedure_record` |

## Classification

| Control | Status |
|---------|--------|
| Procedure hard-gate (in_progress/completed) | **PASS** |
| Plan-level hard-gate | **BLOCKED** (clinical decision pending) |
| Consent expiry | **NOT APPLICABLE** |
| Clinical professional sign-off of policy | **BLOCKED** |
