# P2.1 — Entitlement Shadow Evaluation

**Baseline HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**Migration:** `0024_entitlement_shadow` (data-only feature map)  
**Mode:** Shadow only — **does not enforce** and must not block workflows.

## Existing model audit (P2.0)

| Asset | Structure | Notes |
|-------|-----------|-------|
| `subscription_plans` | family_code + version; max_*; features JSONB | Immutable revisions |
| `subscriptions` | 1:1 tenant; status enum | Commercial axis ≠ `tenants.status` |
| `subscription_events` | Append-only history | Not used for per-evaluation logging |
| Seeded features (pre-0024) | Often only `informational_limits` after test reseed | 0024 + conftest normalize booleans |

## Entitlement contract

Central module: `backend/app/modules/subscriptions/entitlements.py`.

| Field | Meaning |
|-------|---------|
| Plan identity | code, family_code, version, name, catalog `is_active` |
| Subscription | status, trial/period/grace dates, `commercially_usable` |
| Features | known boolean keys from `plan.features` |
| Limits | `max_staff_seats`, `max_locations`, `max_practitioners` |
| Usage | measured or `available: false` |
| Evaluation | result + reason + `would_deny_if_enforced` + `evaluation_mode=shadow` |
| Enforcement | always `enforcement_active: false` in P2.1 |

### Supported keys

| Key | Type | Source | Measurement |
|-----|------|--------|-------------|
| `max_staff_seats` | limit | plan column | Active memberships with `role.name != 'patient'`. Pending invites excluded. |
| `max_locations` | limit | plan column | `locations.is_active` |
| `max_practitioners` | limit | plan column | Approved verifications + active practitioner (≠ staff seats) |
| `patient_portal` | feature | features JSON | boolean |
| `inventory` | feature | features JSON | boolean |
| `operations_dashboard` | feature | features JSON | boolean |
| `clinic_billing` | feature | features JSON | boolean |
| `staff_workforce` | feature | features JSON | boolean |

### Unsupported (always `unavailable`)

| Key | Why |
|-----|-----|
| `max_monthly_appointments` | No plan quota column / commercial period definition |
| `max_storage_bytes` | `size_bytes` incomplete; not a tenant storage ledger |
| `advanced_reports` | Not on catalog plans |
| `custom_branding` | Not on catalog plans |

## Subscription-state decision matrix (shadow)

| Status | `commercially_usable` | Feature/limit shadow |
|--------|----------------------|----------------------|
| trial / active / past_due / grace | true | Evaluate features/limits normally |
| suspended / cancelled / expired | false | `subscription_inactive` |
| missing subscription | unresolved | `unknown` / notes `missing_subscription` |
| missing plan revision | unresolved | notes `missing_plan_revision` |
| inactive catalog revision still assigned | usable if status allows | note `plan_revision_inactive_in_catalog`; historical limits still applied |

## Shadow result codes

- `allowed`
- `would_exceed_limit`
- `feature_not_included`
- `subscription_inactive`
- `unavailable`
- `unknown`

Increment probes use key suffix `__increment` with `probe=create_one` (diagnostic only).

## Permission vs feature

- User `require(permission)` remains authoritative for API access.
- Plan features do **not** grant permissions.
- Permissions do **not** grant plan features.
- Shadow reports commercial dimension only.

## Observability

- Structured log event `entitlement_shadow_resolved` (tenant_id, plan_code, status) — no PHI/clinical.
- No high-volume evaluation table; `subscription_events` unchanged.

## API / UI

- `GET /api/v1/tenants/{tenant_id}/entitlements` — `subscription.read` + tenant match.
- `/subscription` page shows shadow card labeled **not enforced**.

## Why no enforcement yet

P2.1 proves resolution, measurement, and decision semantics. Blocking invite/location/practitioner create belongs in **P2.2** after concurrent-safe count locks and product sign-off.

## P2.2 prerequisites

1. Atomic seat/location/practitioner checks under row locks.
2. Product rules for pending invite reservation.
3. Grace/past_due write-gate matrix (expanding vs read).
4. Explicit non-coupling to `tenants.status` / portal reads.
5. Metrics/alerts on `would_deny_if_enforced` rates in shadow.
