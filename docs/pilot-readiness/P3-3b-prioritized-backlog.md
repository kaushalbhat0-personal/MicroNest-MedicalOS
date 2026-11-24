# P3.3b — Prioritized backlog

**HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**Live professional findings:** **none** (sessions PENDING)  
**Sources in force:** P3.0 security · P3.2/P3.3 agent observations · P3.4 WhatsApp share (done)

Do not promote a single participant request to a universal requirement without corroboration.

---

## Ranked items

| ID | Evidence source | Observed problem | User impact | Confidence | Sev | Proposed response | Further validation? |
|----|-----------------|------------------|-------------|------------|-----|-------------------|---------------------|
| FB-01 | P3.0 security | Client-supplied document `storage_key` | Prod PHI / shared bucket risk | High | **P0** | Server-bound tenant-prefixed keys; engineering phase | Security review after fix |
| FB-02 | P3.0 security | Dental consent not hard-gated | Procedure without enforced consent | High | **P0** | Hard-gate before procedure actions | Clinical + security |
| FB-02b | P3.0 | Shared prod object-storage isolation | Cross-tenant file risk if misconfigured | High | **P0** | Tenant isolation on storage | With FB-01 |
| FB-08 | P3.0–P3.2 | No production email for invite/verify | Self-serve onboarding blocked | High | **P1** | Notification provider ops | Ops |
| FB-03 | P3.3 agent visual | Billing/estimate needs patient UUID paste | Slows billing staff | Medium–High | **P2** | Patient search/picker | Confirm in dentist + eye sessions |
| FB-04 | P3.0 / nav | “Plans” label collision | Wrong destination | Medium | **P2** | Rename / IA split | Light confirm |
| FB-14 | P3.3b agent (login) | Login JSON `tenants: []` while `/auth/me` lists tenants | Empty workspace picker after sign-in | Medium | **P2** | Fix tenant_options on login path | Reproduce + eng fix |
| FB-05 | P3.3 agent | Odontogram on secondary Dental tab | Discoverability | Low–Med | **P3** | Facilitation or IA tweak | **Dentist session** |
| FB-06 | P3.3 agent | “Last visit: None” vs encounters on file | Confusing overview | Low–Med | **P3** | Verify copy/logic | Optional |
| FB-07 | P3.3 seed | Demo seed appointment/plan/follow-up 422 | Facilitator friction | High (ops) | **P3** | Fix seed payloads | Facilitator only |
| FB-11 | Eye discovery | Ophthalmology structured clinical | Specialty gap | Unknown | — | **Do not build** until live answers | **Eye session** |
| FB-12 | Dentist live | — | — | — | — | Fill after session | **PENDING** |
| FB-13 | Eye live | — | — | — | — | Fill after session | **PENDING** |

---

## Done / out of scope this phase

| Item | Status |
|------|--------|
| P3.4 WhatsApp-assisted share (wa.me) | Done — click-to-chat only |
| X-ray acquisition | Out of scope |
| Portal download / reschedule | Deferred |
| Ophthalmology module | Blocked on discovery |
| Product code changes in P3.3b | **None** (research phase) |

---

## Security gate (unchanged)

Real-patient-data use remains **blocked** until FB-01 / FB-02 / FB-02b are independently remediated and verified. Synthetic pilots remain OK with local storage.
