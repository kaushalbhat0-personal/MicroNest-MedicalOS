# P3.3 — Eye specialist discovery

**Status:** Session **PENDING** — no eye specialist has participated yet.  
**HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**Scope:** Validate **generic clinic** workflows only. Do **not** implement ophthalmology-specific clinical features in P3.3.  
**Do not fabricate answers.** Record the specialist’s actual responses in the tables below during a live session.  
**Live session tracker:** `P3-3b-eye-specialist-validation.md` · kit: `P3-3b-observation-log.md`

## Premise

Dental workflows do **not** translate directly to ophthalmology. The eye specialist session validates that the generic clinic shell (patients, schedule, reception, encounters, Rx, billing, follow-ups, portal) is usable, and captures specialty requirements for a later phase.

Specialty code `ophthalmology` may already exist for workspace tagging; there is **no** ophthalmology clinical module.

## Synthetic environment

Same local stack as dentist report. Prefer a separate synthetic workspace labeled `P33 DEMO Eye Clinic` if running both sessions in parallel (create via `/onboarding` or seed). Never use real patient data.

## Generic clinic walkthrough tasks

| ID | Task | Start | Expected | Actual | Steps | Confusion | Severity | Feedback |
|----|------|-------|----------|--------|-------|-----------|----------|----------|
| E-G1 | Workspace entry / login | `/login` | Enter clinic shell | *pending* | | | | |
| E-G2 | Dashboard | `/` | Understand today | *pending* | | | | |
| E-G3 | Register patient | `/patients` | Create chart | *pending* | | | | |
| E-G4 | Search patient | `/patients` | Find synthetic patient | *pending* | | | | |
| E-G5 | Book appointment | `/schedule` | Book with approved practitioner | *pending* | | | | |
| E-G6 | Reception | `/reception` | Check-in / queue | *pending* | | | | |
| E-G7 | Patient history | Patient Timeline | Chronology clear | *pending* | | | | |
| E-G8 | Generic consultation notes | Encounter Notes | SOAP usable | *pending* | | | | |
| E-G9 | Prescriptions | Encounter Rx tab | Create / sign path clear | *pending* | | | | |
| E-G10 | Estimates / billing | `/billing/*` | Create estimate/invoice | *pending* | | | | |
| E-G11 | Follow-ups | `/follow-ups` | Create / list | *pending* | | | | |
| E-G12 | Patient portal | Enroll + `/portal` | Permitted views only | *pending* | | | | |

## Discovery questions (record verbatim answers)

### Patient intake

| # | Question | Answer |
|---|----------|--------|
| Q1 | What information must be captured at first visit? | *pending* |
| Q2 | Which identifiers matter (MRN, Aadhaar, insurance, referring doctor)? | *pending* |
| Q3 | How do walk-ins differ from scheduled new patients? | *pending* |

### Consultation sequence

| # | Question | Answer |
|---|----------|--------|
| Q4 | Typical room/step sequence for a routine visit? | *pending* |
| Q5 | Who enters data (doctor, optometrist, counselor, receptionist)? | *pending* |
| Q6 | What must be visible before the doctor starts examination? | *pending* |

### Clinical documentation

| # | Question | Answer |
|---|----------|--------|
| Q7 | Is SOAP adequate, or do you need structured exam forms? | *pending* |
| Q8 | Which findings are mandatory vs optional? | *pending* |
| Q9 | How do you document laterality (OD/OS/OU)? | *pending* |

### Measurements and examination

| # | Question | Answer |
|---|----------|--------|
| Q10 | Which measurements are routine (VA, refraction, IOP, etc.)? | *pending* |
| Q11 | Units, devices, and who records them? | *pending* |
| Q12 | Do values need trending over visits? | *pending* |

### Prescriptions

| # | Question | Answer |
|---|----------|--------|
| Q13 | Spectacle Rx vs medication Rx — separate flows? | *pending* |
| Q14 | Required fields for glasses/contact lens prescriptions? | *pending* |
| Q15 | Print / share expectations? | *pending* |

### Equipment and external systems

| # | Question | Answer |
|---|----------|--------|
| Q16 | Which devices must integrate (auto-refractor, OCT, etc.)? | *pending* |
| Q17 | Current systems to replace or coexist with? | *pending* |

### Imaging and documents

| # | Question | Answer |
|---|----------|--------|
| Q18 | What images/reports are stored per visit? | *pending* |
| Q19 | Who uploads; who needs to view at chairside? | *pending* |
| Q20 | Any PACS / cloud viewer today? | *pending* |

### Follow-up and reporting

| # | Question | Answer |
|---|----------|--------|
| Q21 | Common recall intervals and reasons? | *pending* |
| Q22 | Reports needed for referring doctors or surgery centers? | *pending* |
| Q23 | What would block you from using a generic clinic OS daily? | *pending* |

## Agent notes (not specialist answers)

- Generic encounter Notes/Vitals/Diagnoses/Prescriptions tabs are available without dental-specific UI.
- Dental odontogram must **not** be presented as the eye charting solution.
- Billing UUID paste friction (see dentist report) will affect eye clinic staff equally.
- Ophthalmology specialty requirements remain **discovery-only** until a later phase.

## Session log

| Field | Value |
|-------|--------|
| Participant | *pending* |
| Date / duration | *pending* |
| Facilitator | *pending* |
| Comfort with generic clinic (1–5) | *pending* |
| Must-have before pilot with real patients | *pending* |

## Verdict for eye track

**Not professionally validated.** Discovery questionnaire and generic walkthrough are ready for a facilitated session. No ophthalmology features implemented in P3.3.
