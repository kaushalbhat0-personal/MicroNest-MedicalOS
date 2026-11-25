# Encounter Lifecycle and Consent

## Encounter states

`open` → `closed` only. No `in_progress`.

### Close requirements (backend)

1. Finalized clinical note **or** `note_waiver`
2. Vitals observation **or** `vitals_waiver`
3. No draft prescriptions
4. No draft treatment plans

Desktop close dialog defaults waivers **off**; operator may opt in. Server errors surface without inventing success.

## Consent

| Domain | Gates clinical write? | Desktop behavior |
|--------|----------------------|------------------|
| Dental procedure consent | Yes for procedure `in_progress`/`completed` | Procedure status transitions not offered in M7; documented |
| Plan activate | No (existing backend policy) | Activate not offered |
| Communication consent | WhatsApp/outbound only | No auto WhatsApp; follow-up create only |

## Follow-ups

POST `/follow-ups` with `category=encounter`, `source_id=encounterId`. No reminder delivery invented.

## Timeline

Closing and clinical events appear per backend timeline rules (encounters, diagnoses on close path, signed rx, plans, follow-ups). Clinical **notes** and **vitals** are not separate timeline kinds (backend gap — documented).
