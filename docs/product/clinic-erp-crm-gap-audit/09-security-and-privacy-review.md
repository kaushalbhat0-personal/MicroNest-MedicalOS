# 09 — Security and privacy review (gap-audit lens)

## Strengths (verified)

| Control | Evidence |
|---------|----------|
| Server-derived tenant match | `match_tenant` 404-oracle |
| Permission catalog | `require(P.*)` — no role string checks in prod paths |
| Portal ownership choke point | `portal_service.active_link` → `patient_id` never from client |
| Draft / internal hiding | Portal filters drafts; storage keys never returned |
| Isolation suites | RLS, scheduling isolation, portal security, two-tenant pilots |
| Audit refs-only | Appointment/patient actions without PHI payloads |
| Session cookies | HttpOnly; refresh rotation |

## Gaps / risks for the pilot slice

| Risk | Classification | Mitigation in slice |
|------|----------------|---------------------|
| `PATIENT_UPDATE` unused / not seeded | Gap | Add to seed roles + PATCH with audit |
| Portal availability leaking other patients | Design risk | Return **slot start/end only** — never patient/staff notes |
| Portal book without new permission | Authz gap | Add `portal.appointment.book`; keep cancel separate |
| Draft treatment plans visible | Needs improvement | Defer strict release unless touching dental portal filter |
| CSV import abuse | Risk | Staff-only `patient.create`; size limits; synthetic data in tests |
| WhatsApp auto-send | Out of scope | Click-to-chat `wa.me` only — user initiated |
| Client-supplied tenant as proof | Already denied | Preserve `match_tenant` |

## Explicit non-claims

This audit does **not** assert HIPAA/GDPR/DPDP legal compliance. Isolation and release rules are engineering controls only.
