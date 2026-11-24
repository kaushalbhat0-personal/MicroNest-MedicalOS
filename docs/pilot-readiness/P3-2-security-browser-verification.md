# P3.2 — Security browser verification

**HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**Source of truth:** API authorization (not hidden UI buttons)

## Browser / API checks executed

| Check | Method | Result |
|-------|--------|--------|
| Patient A staff cannot read Patient B by id under tenant A | `GET /tenants/{A}/patients/{B}` → 403/404 | Pass |
| User cannot operate under unrelated tenant header | `GET /tenants/{B}` with membership only in A → 401/403/404 | Pass |
| Receptionist cannot approve practitioners | `POST .../verification` as receptionist → 401/403 | Pass |
| Wrong account cannot accept invite | Authenticated accept mismatch message | Pass |
| Invalid / reused invite token | Opaque gone/invalid UX | Pass |
| Portal unauthenticated access | `/portal` → `/login` | Pass |
| Portal user does not see Approve practitioner admin path | Navigate `/admin` as portal identity | Pass (no approve affordance) |

Playwright file: `apps/web/e2e/authenticated-journeys.spec.ts` · project `desktop-1280`.

## Backend isolation (serial, `healthcare_os_test`)

```text
.\.venv\Scripts\python.exe -m pytest tests/isolation -q
# 38 passed

.\.venv\Scripts\python.exe -m pytest tests -k portal -q
# 33 passed
```

Always serial on the shared test database.

## P3.0 findings — status

| Finding | P3.2 status |
|---------|-------------|
| Client-supplied document `storage_key` | **Unresolved** — no implementation change this phase; still Risk → Blocker for shared prod object storage |
| Dental consent hard-gating | **Unresolved** — workflow exists; no hard stop before procedure |
| Tenant RLS / portal isolation | Reinforced by browser + pytest green |

## Pilot data policy

- Synthetic emails only (`p32.*@example.com`).
- No real patient data.
- **Real-patient-data onboarding remains blocked** while document `storage_key` and dental consent hard-gate stay open for production PHI.
- Synthetic-data pilot rehearsal is approved for local/dev with local storage.
