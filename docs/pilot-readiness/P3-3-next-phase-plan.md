# P3.3 — Next phase plan

**Based on:** P3.0–P3.2 readiness + P3.3 session guides (professional feedback still pending)  
**HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3`

## Immediate next steps (before claiming professional validation)

1. **Run dentist facilitated session** using `P3-3-dentist-usability-report.md`; fill Actual / Feedback columns.  
2. **Run eye specialist session** using `P3-3-eye-specialist-discovery.md`; record verbatim answers.  
3. Merge live findings into `P3-3-feedback-backlog.md` (replace FB-12 / FB-13 placeholders).  
4. Re-prioritize only after at least one of each specialty session, unless a P0 appears.

## Implementation priorities (provisional)

| Order | Item | Rationale | Depends on |
|-------|------|-----------|------------|
| 1 | Server-bound document `storage_key` + tenant storage isolation | Unlocks real-patient discussion | Security workstream |
| 2 | Dental consent hard-gate | Clinical safety for dental procedures | Security / dental |
| 3 | Patient picker on billing/estimate create (replace UUID paste) | Clear P2 from agent review; likely confirmed by both specialties | Small UX + API list |
| 4 | Nav “Plans” rename / IA split | Recurring confusion | Copy/IA |
| 5 | Polish demo seed (appointment `start`, follow-up fields, procedure codes) | Faster facilitators | Scripts only |
| 6 | Dentist-confirmed charting / plan friction fixes | Only after D-session | Live feedback |
| 7 | Ophthalmology structured requirements design | Only after E-session discovery | Live answers — **no build before** |
| 8 | Production notification provider | Self-serve invites/verify | Ops |

## Explicit non-goals for next short phase

- Razorpay auto-renewal / SaaS payment expansion (P2.5 freeze)  
- Speculative ophthalmology module before discovery answers  
- X-ray acquisition / annotation  
- Portal document download / reschedule (unless pilot contract requires)  
- Enabling real PHI while FB-01/FB-02 open  

## Pilot data policy (unchanged)

| Mode | Status |
|------|--------|
| Synthetic-data rehearsal | **Approved** (P3.2) |
| Real-patient-data use | **Blocked** |

## Suggested phase labels

| Phase | Focus |
|-------|--------|
| P3.3b | Complete live dentist + eye sessions; update backlog with real feedback |
| P3.4 | Security hard fixes (storage_key, consent gate) — prerequisite for PHI |
| P3.5 | High-confidence UX fixes from sessions (picker, IA, charting friction) |
| P3.6+ | Specialty depth (ophthalmology) only with written requirements |

## Success criteria for “professionals can use daily”

- At least one dentist session with no unresolved P0/P1 in dental daily path  
- At least one eye session confirming generic clinic path is workable **or** listing must-haves  
- FB-01/FB-02 resolved before any real-patient pilot  
- No skipped auth journeys counted as pass (preserve P3.2 discipline)  
