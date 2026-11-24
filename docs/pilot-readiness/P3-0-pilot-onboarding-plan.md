# P3.0 — Pilot Onboarding Plan (Assisted)

**Mode:** Operator-assisted. Clinicians use the staff/portal UI after API bootstrap.  
**Data:** Synthetic patients only. No real PHI.  
**Payments:** Clinic AR only. SaaS Razorpay frozen at P2.5 — mock/off for pilots.

## A. Environment checklist

1. PostgreSQL 19 local DB migrated to `0027_saas_payment_reliability`.  
2. API + Next.js web against a non-production database.  
3. `NOTIFY_PROVIDER=dev-console` + `DEV_NOTIFICATIONS_ALLOW=true` for verify links in logs.  
4. Run pytest **serially** on `healthcare_os_test` (never parallel against the same DB).

## B. Bootstrap clinic A — dentist

```text
1. POST /api/v1/auth/signup  (synthetic email)
2. Copy DEV verification token from API logs → POST /api/v1/auth/verify
3. POST /api/v1/auth/login
4. POST /api/v1/workspaces
   Idempotency-Key: <uuid>
   body: clinic_name, slug, timezone, specialty_codes: ["dental"], location_name
5. POST /api/v1/tenants/{id}/verification  → approve owner practitioner
6. (Optional) POST /api/v1/tenants/{id}/portal-links for a synthetic patient user
7. Hand clinic to dentist: login → select tenant → /patients → /schedule → /reception
```

## C. Bootstrap clinic B — eye specialist (generic)

Same as B with `specialty_codes: ["ophthalmology"]` (discovery maturity).  
Expect **generic** EMR only: patients, schedule, encounters, Rx, billing, follow-ups, portal.  
Do **not** promise ophthalmology charts, refraction calculators, or imaging workflows.

## D. Dentist day-1 script (synthetic)

1. Register patient; book appointment; check-in; confirm queue token.  
2. Open encounter; note + diagnosis; odontogram finding; treatment plan draft.  
3. Estimate → invoice → payment → receipt (clinic billing).  
4. Create follow-up; generate WhatsApp click-to-chat if phone present.  
5. Portal: enroll via API; patient books/cancels; confirm no cross-patient access.

## E. Eye specialist day-1 script (synthetic)

1–3 as generic clinic (no dental plans required).  
4. Complete **discovery checklist** below — capture answers; no code changes without validation.

## F. Ophthalmology discovery checklist

| # | Topic | Questions for specialist |
|---|-------|--------------------------|
| 1 | Intake | What demographics, history, allergies, current glasses/CL data are mandatory? |
| 2 | Consultation | Typical visit types (refraction, glaucoma, retina, pre-op)? |
| 3 | Documentation | Preferred note structure; templates needed? |
| 4 | Prescriptions | Spectacle Rx fields; CL Rx; systemic Rx overlap? |
| 5 | Measurements | VA, IOP, refraction, biometry — devices used? |
| 6 | Equipment | Which systems must stay external (OCT, VF, EMR)? |
| 7 | Images/docs | What must attach to chart vs stay on device? |
| 8 | Follow-ups | Recall intervals by diagnosis? |
| 9 | Portal | What should patients see (Rx, reports, appointments)? |
| 10 | Reporting | Daily/clinic KPIs required in first 30 days? |

## G. Explicit deferrals (sign before pilot)

- SaaS subscription checkout / Razorpay live  
- Portal document download  
- Portal reschedule  
- Self-serve workspace wizard  
- Automated WhatsApp sending  
- Ophthalmology specialty module  

## H. Rollback / safety

- Suspend tenant (`tenants.status`) for abuse — not for billing delinquency.  
- Portal remains readable under commercial delinquency (P2.3).  
- Do not disable RLS for demos.
