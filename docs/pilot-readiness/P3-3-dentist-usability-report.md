# P3.3 — Dentist usability report

**Status:** Session **PENDING** — no dentist has participated yet.  
**HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**Environment:** local API `localhost:8000` · web `localhost:3000` · synthetic `P33 DEMO` data only  
**Do not treat this document as professional validation.**  
**Live session tracker:** `P3-3b-dentist-validation.md` · kit: `P3-3b-observation-log.md`

## Purpose

Guided usability session for a dentist covering Dental ERP + generic clinic workflows. This file is the facilitator script and observation log. User feedback cells stay empty until a real session occurs.

## Synthetic demo fixture

| Item | Value |
|------|--------|
| Owner email | `p33.demo.owner@example.com` (password via env / seed only) |
| Clinic | `P33 DEMO Dental Clinic …` |
| Patient | `P33 DEMO Patient Alpha` (`+910000000033`) |
| Seed | `scripts/p33_demo_seed.py` |
| Fixture JSON | `docs/ui-ux/screenshots/p33-demo-fixture.json` |

Never use real patient names, phones, notes, or documents in the session.

## Facilitator checklist (before session)

1. API health: `GET http://localhost:8000/api/healthz` → ok  
2. Web: `http://localhost:3000`  
3. Seed demo if needed: `python scripts/p33_demo_seed.py`  
4. Confirm practitioner approved; booking uses approved practitioners only  
5. Screenshots folder ready under `docs/ui-ux/screenshots/`  
6. Remind participant: synthetic data only; think-aloud preferred  

## Walkthrough tasks

Record during the live session. Severity: P0–P3 (see backlog).

### A. First use

| ID | Task | Role | Start | Expected | Actual | Steps | Confusion | Severity | User feedback |
|----|------|------|-------|----------|--------|-------|-----------|----------|---------------|
| D-A1 | Login | Dentist/owner | `/login` | Reach clinic shell | *pending* | | | | |
| D-A2 | Workspace overview | Owner | `/` | Understand today attention | *pending* | | | | |
| D-A3 | Clinic setup | Owner | `/onboarding` | See setup steps / resume | *pending* | | | | |
| D-A4 | Practitioner approval | Owner | `/onboarding` or `/admin` | See approved/pending clearly | *pending* | | | | |
| D-A5 | Staff access | Owner | `/staff` | Understand invite path | *pending* | | | | |

### B. Daily operations

| ID | Task | Role | Start | Expected | Actual | Steps | Confusion | Severity | User feedback |
|----|------|------|-------|----------|--------|-------|-----------|----------|---------------|
| D-B1 | Dashboard scan | Dentist | `/` | Find today’s work | *pending* | | | | |
| D-B2 | Today’s appointments | Reception/dentist | `/` or `/schedule` | See list or empty CTA | *pending* | | | | |
| D-B3 | Reception board | Reception | `/reception` | Waiting / check-in clear | *pending* | | | | |
| D-B4 | Walk-in registration | Reception | `/reception` | Register walk-in | *pending* | | | | |

### C. Patient CRM

| ID | Task | Role | Start | Expected | Actual | Steps | Confusion | Severity | User feedback |
|----|------|------|-------|----------|--------|-------|-----------|----------|---------------|
| D-C1 | Search patient | Reception | `/patients` | Find P33 DEMO Patient Alpha | *pending* | | | | |
| D-C2 | Register new patient | Reception | `/patients` | Create + open chart | *pending* | | | | |
| D-C3 | Open Patient 360° | Dentist | `/patients/{id}` | Overview scannable | *pending* | | | | |
| D-C4 | Chronological history | Dentist | Timeline tab | Understand sequence | *pending* | | | | |
| D-C5 | Contacts / follow-ups | Staff | Care / Follow-ups | Find next action | *pending* | | | | |

### D. Dental consultation

| ID | Task | Role | Start | Expected | Actual | Steps | Confusion | Severity | User feedback |
|----|------|------|-------|----------|--------|-------|-----------|----------|---------------|
| D-D1 | Open encounter | Dentist | `/encounters` or chart | Encounter opens | *pending* | | | | |
| D-D2 | Clinical notes (SOAP) | Dentist | Notes tab | Draft / finalize note | *pending* | | | | |
| D-D3 | Dental chart (odontogram) | Dentist | Dental tab | Select tooth, record finding | *pending* | | | | |
| D-D4 | Treatment plan | Dentist | `/dental/plans` | Create / open plan | *pending* | | | | |
| D-D5 | Estimate | Dentist/billing | `/billing/estimates` | Create estimate | *pending* | | | | |

**Out of scope:** X-ray acquisition / annotation.

### E. Billing and follow-ups

| ID | Task | Role | Start | Expected | Actual | Steps | Confusion | Severity | User feedback |
|----|------|------|-------|----------|--------|-------|-----------|----------|---------------|
| D-E1 | Review invoice | Billing | `/billing/invoices` | Find / create draft | *pending* | | | | |
| D-E2 | Record synthetic payment | Billing | Payments | Payment recorded | *pending* | | | | |
| D-E3 | Outstanding balance | Dentist | Patient 360 / billing | Server balance visible | *pending* | | | | |
| D-E4 | Create follow-up | Staff | `/follow-ups` | Due item created | *pending* | | | | |
| D-E5 | WhatsApp user-initiated | Staff | Patient Care | Consent + open link | *pending* | | | | |

### F. Patient portal

| ID | Task | Role | Start | Expected | Actual | Steps | Confusion | Severity | User feedback |
|----|------|------|-------|----------|--------|-------|-----------|----------|---------------|
| D-F1 | Enroll synthetic patient | Staff | Patient Details | Portal link created | *pending* | | | | |
| D-F2 | Patient login | Patient | `/login` | Reach `/portal` | *pending* | | | | |
| D-F3 | Permitted information | Patient | Portal home | Appointments/records only | *pending* | | | | |

## Agent product observations (not clinician feedback)

Captured 2026-11-24 against synthetic demo; classify preference vs defect carefully.

| Observation | Type | Suggested severity |
|-------------|------|--------------------|
| Dashboard quick actions + attention metrics readable for empty day | Usability (positive) | — |
| Patient 360 overview cards + relationship snapshot clear | Usability (positive) | — |
| Invoice create asks to **paste patient UUID** | Usability problem | **P2** |
| Odontogram lives under encounter **Dental** tab (not default Notes) | Facilitation note / possible P3 discoverability | P3 |
| “Last visit: None recorded” while “1 encounter(s) on file” | Possible consistency issue | P3 (verify) |
| Treatment plan seed needs valid procedure catalog codes | Missing/ops friction for demos | P3 |
| Close-encounter gates explained in UI | Positive clinical safety copy | — |

## Screenshots (synthetic)

Under `docs/ui-ux/screenshots/`: `p33-dashboard.png`, `p33-patients.png`, `p33-patient-360.png`, `p33-schedule.png`, `p33-reception.png`, `p33-encounter-notes.png`, `p33-dental-chart.png`, `p33-dental-plans.png`, `p33-billing.png`, `p33-estimates.png`, `p33-follow-ups.png`, `p33-onboarding.png`, `p33-mobile-patients.png`.

## Session log

| Field | Value |
|-------|--------|
| Participant | *pending* |
| Date / duration | *pending* |
| Facilitator | *pending* |
| Overall comfort (1–5) | *pending* |
| Would use daily? | *pending* |
| Top 3 requests | *pending* |

## Verdict for dentist track

**Not professionally validated.** Product is ready for a facilitated synthetic walkthrough; findings above are agent observations + empty session tables awaiting real feedback.
