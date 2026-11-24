# P3.3 — Feedback backlog

**HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**Sources:** Agent product walkthrough (2026-11-24) · Prior P3.0–P3.2 findings · Live professional sessions (**none yet**)

Severity: **P0** security/integrity/blocker · **P1** seriously disrupts work · **P2** significant friction · **P3** minor.

## Ranked backlog

| ID | Finding | Source | Class | Severity | Priority | Disposition |
|----|---------|--------|-------|----------|----------|-------------|
| FB-01 | Client-supplied document `storage_key` | P3.0 security | Security / missing hard control | **P0** (prod PHI) | 1 | Open — blocks real-patient-data |
| FB-02 | Dental consent not hard-gated before procedure | P3.0 security | Security / clinical safety | **P0** (prod clinical) | 2 | Open — tracked separately |
| FB-03 | Invoice/estimate create requires pasting patient UUID | P3.3 agent visual | Usability problem | **P2** | 3 | Deferred — patient picker / search select |
| FB-04 | “Plans” nav label collides (treatment vs SaaS catalog) | P3.0 / nav | Usability problem | **P2** | 4 | Deferred — rename/IA |
| FB-05 | Odontogram under secondary Dental tab (discoverability) | P3.3 agent | Usability / preference boundary | **P3** | 5 | Defer until dentist session confirms |
| FB-06 | Patient 360 “Last visit: None” vs encounters on file | P3.3 agent | Possible consistency bug | **P3** | 6 | Verify then fix if confirmed |
| FB-07 | Demo seed: appointment/plan/follow-up payload mismatches | P3.3 seed | Ops / missing fixture polish | **P3** | 7 | Improve seed for facilitators |
| FB-08 | Production email for invite/verify/reset | P3.0–P3.2 | Missing backend dependency | **P1** (self-serve) | 8 | Ops dependency — not claimed green |
| FB-09 | Portal document download / reschedule | P3.0 | Deferred feature | — | 9 | Explicitly out of pilot scope |
| FB-10 | X-ray acquisition / annotation | Product boundary | Deferred feature | — | 10 | Out of scope |
| FB-11 | Ophthalmology structured exam / refraction / IOP | Eye discovery | Specialty requirement | — | 11 | **Pending** specialist answers — do not build yet |
| FB-12 | Live dentist usability outcomes | Dentist session | *pending* | — | — | Fill after session |
| FB-13 | Live eye specialist answers | Eye session | *pending* | — | — | Fill after session |

## Classification guide used

| Class | Meaning |
|-------|---------|
| Usability problem | Observed friction that would slow most users |
| Individual preference | Taste; not universal — wait for multiple users |
| Missing backend functionality | API/product gap, not just UI polish |
| Unverified behavior | Suspected; needs reproduce or clinician confirm |
| Specialty-specific requirement | Eye/dental domain need — may not apply cross-specialty |
| Security | Isolation, consent, storage, authz |

## Implemented in P3.3

| Change | Risk | Notes |
|--------|------|-------|
| `scripts/p33_demo_seed.py` | Low | Synthetic demo fixture via API |
| `apps/web/e2e/p33-visual-capture.spec.ts` | Low | Screenshot capture with loading waits |
| Session guides + backlog docs | None | No authz or payment changes |

No authorization weakening. No SaaS payment expansion. No speculative clinical features.

## Explicitly not done

- Real-patient-data enablement  
- Claiming FB-01 / FB-02 resolved  
- Ophthalmology clinical module  
- Razorpay / auto-renewal  
- Wholesale redesign  
