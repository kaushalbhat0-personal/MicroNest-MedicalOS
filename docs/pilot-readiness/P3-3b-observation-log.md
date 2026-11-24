# P3.3b — Session observation log & facilitator kit

**HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**Professional sessions:** **PENDING** — no dentist or eye specialist participated in this agent run.  
**Do not invent quotes, scores, or approval.**

---

## Consent & anonymization (read aloud)

1. Participation is voluntary; the participant may stop at any time.  
2. We use **synthetic** clinic data only (`P33 DEMO…`). Do not enter real patient names, phones, charts, or documents.  
3. We record **role** (e.g. dentist, ophthalmologist), clinic type, and task outcomes — not full legal name unless they consent separately for a named case study.  
4. Quotes are optional; only store quotes the participant agrees to.  
5. Recordings (screen/audio) require explicit consent; default is written notes only.  
6. Data stays in pilot-readiness docs / internal notes; not for marketing without consent.

Facilitator initials: ________  Participant consent: ☐ Yes  Date: ________

---

## Synthetic demo checklist (pre-session)

| Step | Done |
|------|------|
| `GET http://localhost:8000/api/healthz` → ok | ☐ |
| Web `http://localhost:3000` loads | ☐ |
| `python scripts/p33_demo_seed.py` (or known working demo owner) | ☐ |
| Login as demo owner; open **Dashboard** and confirm a `P33 DEMO` workspace appears (if login shell looks empty, refresh or navigate home — see known quirk below) | ☐ |
| Patient `P33 DEMO Patient Alpha` findable under Patients | ☐ |
| Encounter / Dental tab reachable for dentist session | ☐ |
| WhatsApp share available on Staff invite + patient Care (P3.4) | ☐ |
| Screenshots folder `docs/ui-ux/screenshots/` writable | ☐ |
| No real PHI in browser forms | ☐ |

**Known facilitator quirk (agent-observed, 2026-11-24):** `POST /auth/login` JSON may return `tenants: []` while a subsequent `GET /auth/me` with session cookies lists memberships correctly. If the UI shows no workspace after sign-in, refresh home or re-open the app once before the participant starts timed tasks.

**Seed limitations:** appointment / treatment-plan / follow-up auto-seed may 422 (payload/procedure catalog). Create those manually in-session if needed.

---

## Task completion scoring

Use one code per task:

| Code | Meaning |
|------|---------|
| **I** | Independent — completed without facilitator help |
| **A** | Assisted — completed with hints or intervention |
| **F** | Failed — could not complete |
| **N** | Not attempted (time / skip) |
| **P** | Pending — session not run |

Severity for friction (if any): P0 / P1 / P2 / P3 (see backlog doc).

---

## Observation sheet (blank)

| Time | Task ID | Score (I/A/F/N) | Facilitator notes (hesitation, errors, terminology) | Participant suggestion (verbatim if allowed) | Severity |
|------|---------|-----------------|-----------------------------------------------------|----------------------------------------------|----------|
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |

Separate **observed friction** from **suggestions**. Do not lead the participant.

---

## Session meta (fill only when live)

| Field | Dentist session | Eye session |
|-------|-----------------|-------------|
| Status | **PENDING** | **PENDING** |
| Date / duration | — | — |
| Role (not full identity) | — | — |
| Clinic type / setting | — | — |
| Facilitator | — | — |
| Recording consent | — | — |
| Overall comfort 1–5 | — | — |
| Would use for daily ops? | — | — |

---

## Agent pre-session verification (not professional validation)

| Check | Result |
|-------|--------|
| API health | ok (2026-11-24) |
| Web :3000 | 200 |
| Demo seed re-run | Created `p33-demo-11241735`; patient + encounter present |
| Login→tenants in body | Empty on login response; `/auth/me` lists 2 demo tenants |
| Professional participants | **None** |
