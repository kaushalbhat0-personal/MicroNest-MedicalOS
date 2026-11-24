# P3.3b — Next phase plan

**HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**P3.3b outcome:** Facilitator kit + validation templates ready; **live professional sessions still PENDING**.

## Immediate (human-led)

1. Schedule and run **dentist** session → fill `P3-3b-dentist-validation.md` + observation log.  
2. Schedule and run **eye specialist** discovery → fill `P3-3b-eye-specialist-validation.md`.  
3. Merge live findings into `P3-3b-prioritized-backlog.md` (replace FB-12 / FB-13).  
4. Re-rank only after evidence; do not implement specialty modules from speculation.

## Recommended engineering sequence (after or parallel to sessions)

| Order | Phase focus | Gate |
|-------|-------------|------|
| 1 | **Security remediation** — `storage_key` binding + shared storage tenant isolation + dental consent hard-gate | Required before real PHI |
| 2 | **High-confidence UX** — patient picker for billing (FB-03); login tenants response (FB-14); Plans nav rename (FB-04) | Prefer session corroboration for FB-03/04 |
| 3 | **Facilitator polish** — demo seed appointment/plan/follow-up (FB-07) | Non-blocking |
| 4 | **Specialty design** — ophthalmology requirements doc from eye answers only | No build without written requirements + clinical review |

## Explicit non-goals

- Claiming professional validation without sessions  
- Inventing quotes/scores  
- WhatsApp Business / automated messaging  
- SaaS payment expansion (P2.5 freeze)  
- Enabling real-patient-data while P0 security items open  

## Success criteria for “professionally validated”

| Criterion | Status |
|-----------|--------|
| ≥1 dentist session with scored tasks | **Not met** |
| ≥1 eye session with discovery answers | **Not met** |
| No unresolved P0/P1 in daily dental path from that session | N/A |
| Security P0s resolved before real PHI | **Not met** |

## Pilot data policy

| Mode | Status |
|------|--------|
| Synthetic rehearsal | Approved (P3.2) |
| Real patient data | **Blocked** |
