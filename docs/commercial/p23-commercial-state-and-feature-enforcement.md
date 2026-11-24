# P2.3 — Commercial State Gates, Feature Enforcement & Patient Access Separation

**Baseline HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**Migration:** `0025_commercial_gates` (trial feature evaluation map)  
**Module:** `backend/app/modules/subscriptions/commercial_policy.py`

## Operation classification

| Category | Examples | Commercial gate |
|----------|----------|-----------------|
| `capacity_expand` | Invite, seat reactivate, location create/reactivate, practitioner approve | `trial`, `active` only |
| `business_create` | Appointments, encounters, prescriptions, treatment plans | `trial`, `active`, `past_due`, `grace` |
| `feature_mutate` | Inventory creates/adjust/PO, billing create, staff schedules | Business statuses **and** feature true |
| `feature_read` | Operations dashboard | Feature true (commercial not required beyond abuse) |
| `patient_portal_access` | Portal reads, book, cancel | **Ignores commercial**; feature `patient_portal`; abuse via `get_ctx` |
| `portal_enroll` | Staff enrolls portal user | Business statuses + feature |
| `recovery` | Deactivate location, revoke invite, demote staff | Always (if authorized) |
| `read` | Historical records, exports (existing) | Abuse axis only |

## Subscription-state matrix

| Status | Capacity expand | Business create | Portal access | Recovery | Abuse (`tenants.status`) |
|--------|-----------------|-----------------|---------------|----------|--------------------------|
| trial / active | Yes | Yes | Yes* | Yes | Separate |
| past_due / grace | **No** | Yes | Yes* | Yes | Separate |
| expired / cancelled / suspended | No | **No** | Yes* | Yes | Separate |
| missing | No | No | Yes* if feature | Yes | Separate |

\*Portal access requires `patient_portal` feature + active portal link + `tenants.status=active`.

## Recovery policy

Authorized owners/admins may always: deactivate locations, revoke invites, deactivate staff (subject to last-admin), read subscription, reduce usage. Commercial delinquency does not block recovery.

## Central write policy

`assert_operation_allowed` / `assert_business_create` / `assert_feature` / `assert_portal_access` / `assert_portal_enroll`.

Capacity still goes through `enforcement.assert_capacity` (advisory lock unchanged). Capacity expand statuses imported from this policy (`CAPACITY_EXPAND_STATUSES`).

## Feature enforcement matrix

| Feature | Decision | Integration points |
|---------|----------|--------------------|
| `patient_portal` | **Enforced** | `portal_ctx`, book/cancel, enroll |
| `inventory` | **Enforced** | item/supplier/adjust/PO create |
| `operations_dashboard` | **Enforced** | GET operations-dashboard |
| `clinic_billing` | **Enforced** (staff writes) | invoice/estimate/payment create; portal financial reads **not** gated by this flag |
| `staff_workforce` | **Enforced** (schedules) | `create_schedule`; self check-in still permission-gated |

Trial plan enables all five features for evaluation. Starter keeps inventory/staff_workforce off. Growth enables full set.

**Still unavailable:** `max_monthly_appointments`, `max_storage_bytes`, `advanced_reports`, `custom_branding`.

## Portal authorization separation

1. Authenticate session (`get_current_user`).
2. `require(portal.*)` → `get_ctx` (membership + **abuse** `tenants.status==active`).
3. `assert_portal_access` → plan feature only (commercial ignored).
4. Active `portal_links` → server-derived `patient_id`.
5. Publication filters unchanged (closed encounters, signed Rx, etc.).

**Assumptions:** Clinics retain operational duty to provide patients access to their records during SaaS delinquency; abuse/security suspension may still cut access. No claim of jurisdiction-specific legal compliance from architecture alone.

## Security suspension

Unchanged: `get_ctx` hard-fails when `tenants.status != active`. Never set by subscription transitions.

## Capacity regression

P2.2 locks and reservation rules preserved; past_due/grace no longer expand capacity.

## Observability

Structured log `commercial_policy_decision` — tenant_id, category, status, feature, allowed, reason. No PHI.

## P2.4 prerequisites

1. Payment provider + webhooks driving `past_due` / renew.
2. Dunning UX / grace clocks.
3. Optional tighter business-create gates during grace.
4. Metrics on policy denials.
5. Wired abuse-suspend platform API (still separate).
