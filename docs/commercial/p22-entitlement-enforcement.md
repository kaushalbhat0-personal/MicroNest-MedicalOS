# P2.2 — Atomic Entitlement Enforcement

**Baseline HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**Builds on:** P2.0 (`0023`), P2.1 (`0024` + `entitlements.py`)  
**Migration:** none (behavior-only; uses existing columns)  
**Enforced keys:** `max_staff_seats`, `max_locations`, `max_practitioners`

## Approved capacity rules

### Staff seats

| Rule | Decision |
|------|----------|
| Active non-patient membership | Consumes 1 seat |
| Pending, unexpired, non-revoked invite (role ≠ patient) | Reserves 1 seat |
| Soft-expired but still `pending` | **No** reservation (`expires_at > now`) |
| Revoked / accepted invite | No reservation |
| Accept invite | Reservation → membership atomically (`delta=0`) |
| Deactivated membership | Releases seat |
| Owner / admin | Counts (same as any non-patient role) |
| Patient membership / portal enroll | **Never** consumes seats |
| System/service users | No separate class; only memberships/invites count |

### Locations

| Rule | Decision |
|------|----------|
| `locations.is_active = true` | Consumes 1 |
| Soft deactivate | Releases capacity immediately; row retained |
| Reactivate | Requires free capacity |
| Last active location | May be deactivated (no hard last-location lock) |
| Historical records | Unaffected by deactivation |

### Practitioners

| Rule | Decision |
|------|----------|
| Approved verification **and** `practitioner.is_active` | Consumes 1 tenant-level seat |
| Pending / rejected verification | Does not consume |
| Multi-location | Still one practitioner count (no location multiplier) |
| Membership required? | **No** |
| Revoke approval / deactivate | Releases capacity |
| Unrelated profile edits | Not capacity-gated |

## Locking strategy

```
pg_advisory_xact_lock(hashtext('entitlement:' || tenant_id))
```

Acquired in `assert_capacity()` **before** usage read and held until transaction commit/rollback. Same pattern as scheduling/billing. All capacity-consuming create/activate paths call this helper.

Invitation accept also `SELECT … FOR UPDATE` on the invitation row to prevent double-accept.

## Transaction boundaries

1. Lock tenant capacity.
2. Require expanding-write-eligible subscription status (when enforcing).
3. Measure usage (including invite reservations).
4. Deny with `EntitlementExceededError` (`code=entitlement_exceeded`, HTTP 409) or proceed.
5. Perform the business write in the same transaction.

## Subscription write matrix

| Status | Expanding capacity writes | Reduce / deactivate / revoke | Reads |
|--------|---------------------------|------------------------------|-------|
| trial / active / past_due / grace | Allowed (if under limit) | Allowed | Allowed |
| suspended / cancelled / expired | **Denied** (`subscription_inactive`) | Allowed | Allowed |
| missing subscription | **Denied** (`missing_subscription`) | Allowed | Allowed |

`tenants.status` is **not** consulted for commercial gates. Patient record access is not blocked by SaaS delinquency in P2.2.

**Conservative default:** `past_due` and `grace` still allow expansion. Tighten in P2.3 if product requires.

## Integrated enforcement paths

| Path | Key |
|------|-----|
| `create_invitation` | `max_staff_seats` (+1 reservation) |
| `accept_invitation` / authenticated accept | seat convert (`delta=0`) |
| `create_membership` (non-patient) | `max_staff_seats` |
| `update_membership` reactivation / patient→staff | `max_staff_seats` |
| `create_location` | `max_locations` |
| `set_location_active(True)` | `max_locations` |
| `set_verification(approved)` when newly counting | `max_practitioners` |

## Unsupported / not enforced

- `max_monthly_appointments`, `max_storage_bytes`
- Feature flags (`patient_portal`, etc.) — still shadow
- Payment / checkout
- Automatic `tenants.status` changes

## Observability

- Entitlement summary: `enforcement_active=true`, `enforced_keys`, per-eval `evaluation_mode`
- Structured logs: `entitlement_capacity_check` (tenant, key, usage, limit, reason) — no PHI
- No per-evaluation `subscription_events` rows

## Concurrency evidence

Real PostgreSQL tests in `tests/api/test_entitlements_p22_enforcement.py`:

- Competing invites for last seat → 200 + 409; persisted usage = limit
- Accept converts reservation without double-count
- Revoke / soft-expiry release reservations
- Competing location create / reactivate
- Competing practitioner approval
- Patient memberships ignored
- Suspended blocks expansion; deactivation still works
- Cross-tenant isolation
- Permission 403 independent of capacity
- Rollback releases lock with no leaked invite

## P2.3 prerequisites

1. Optional tighter write gates for `past_due` / `grace`
2. Feature-flag enforcement (if product wants)
3. Payment provider + webhook-driven status
4. Metrics on `entitlement_exceeded` rates
5. Invite expiry sweeper (status flip) — optional; soft-expiry already frees capacity
