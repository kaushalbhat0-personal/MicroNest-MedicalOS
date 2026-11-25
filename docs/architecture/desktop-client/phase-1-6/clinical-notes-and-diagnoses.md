# Clinical Notes and Diagnoses

## Notes

| Action | API | Permission | Policy |
|--------|-----|------------|--------|
| Create draft | POST `.../encounters/{id}/clinical-notes` | `clinical.create` | ≥1 of chief_complaint/subjective/objective/assessment/plan; actor must have linked practitioner |
| Finalize | POST `.../clinical-notes/{id}/finalize` | `clinical.create` | draft→finalized; author-only |
| Amend | POST `.../clinical-notes/{id}/amend` | `clinical.create` | finalized only; creates new finalized + marks old amended |
| Edit draft in place | **UNSUPPORTED** | — | UI creates a new draft |

Desktop: SOAP fields + optional finalize-on-save; amend form for finalized notes; no silent overwrite.

## Diagnoses

| Action | API | Permission |
|--------|-----|------------|
| Create | POST `.../diagnoses` | `clinical.create` |
| Catalog | GET `/diagnosis-codes` | `clinical.read` |

XOR `diagnosis_code` **or** `free_text`. Free-text sets review_needed. Desktop supports code search (client filter of catalog) or free text, primary flag.

## Tests

- Backend: `tests/api/test_clinical_api.py`, `tests/service/test_clinical.py`
- Desktop: encounter transition unit test; API evidence note_create/finalize/diagnosis_create
