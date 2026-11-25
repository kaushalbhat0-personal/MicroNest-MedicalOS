# Clinical Security and Consent — M11

## Isolation

- All dental calls use authenticated desktop client + `X-Tenant`
- Cross-tenant dental-conditions probe denied (evidence)
- Location scope on encounter-linked resources
- Practitioner for writes is server-derived (`practitioner_for_user`) / verified

## Consent hard-gate (unchanged)

Server `transition_procedure_record` requires granted consent for `in_progress` and `completed`. Desktop never bypasses 403.

Plan activation remains **not** consent-gated until dentist decision (P3.6).

## Closed encounters

Dental writes follow encounter open rules via clinical/dental services. Desktop disables writes when encounter not open.

## Session hygiene

Workspace switch / logout clears React dental state with remount. No PHI/tokens in evidence files.

## Permissions

| Action | Perm |
|--------|------|
| Chart read | `dental.read` |
| Findings / procedures / consent | `dental.record` |
| Plan lifecycle | `plan.manage` |
