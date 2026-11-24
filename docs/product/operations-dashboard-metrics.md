# P1.3 / P1.4 / P1.5 Operations Dashboard — Metric Definitions

Endpoint: `GET /api/v1/tenants/{tenant_id}/locations/{location_id}/operations-dashboard`

Read-only. No mutations. No audit events on GET.

Workspace capabilities (nav only): `GET /api/v1/tenants/{tenant_id}/workspace-context`

## Date / timezone

| Domain | Day definition |
|--------|----------------|
| Appointments, reception, payments, clinic hours | **Location IANA timezone** service day (same as `reception_queue`) |
| **Ops follow-up KPIs** | **Same location service day** via `count_follow_ups_for_interval(start_utc, end_utc)`. Response field `follow_up_day_basis=location_service_day`. |
| Follow-ups *workspace* list buckets | **UTC calendar day** (unchanged product behavior) |

Optional `day=YYYY-MM-DD` selects a historical service day. Rejected if not ISO or outside ±730 days of UTC today.

DST: bounds use `ZoneInfo` local midnight → UTC; Python `zoneinfo` handles transitions. Near-midnight UTC/local disagreement is expected between ops KPIs and the Follow-ups workspace.

### Follow-up KPI boundaries (ops)

`due_at` is `timestamptz`. Compared as UTC instants against location day `[start_utc, end_utc)`.

| Bucket | Statuses | Predicate |
|--------|----------|-----------|
| due_today | open, in_progress | start ≤ due_at &lt; end |
| overdue | open, in_progress | due_at &lt; start |
| upcoming | open, in_progress, snoozed | due_at ≥ end |

Completed and cancelled are excluded. Snoozed is excluded from due_today/overdue (aligned with workspace bucket rules, different day base).

UI copy: Operations labels KPIs as “location service day”; Follow-ups workspace describes UTC buckets.

## Appointment / reception metrics

**Metrics** use complete SQL `GROUP BY status` COUNTs for the location service-day window (no row cap). Optional `practitioner_id` narrows both metrics and detail.

| Metric | Definition |
|--------|------------|
| `scheduled_today` | Count of all appointments with `start_at` in the service-day window |
| `waiting` | `status IN (scheduled, confirmed)` |
| `checked_in` | `status = checked_in` |
| `completed` | `status = completed` |
| `cancelled` | `status = cancelled` |
| `no_show` | `status = no_show` |
| `in_consultation` | Count of **open encounters** at the location (not an appointment status) |

### Detail list (`todays_appointments` + `appointments_list`)

Bounded dedicated query (`APPOINTMENT_DETAIL_LIMIT = 50`), ordered by `start_at`, optional status filter. Independent of the reception board’s 200-row cap.

| Field | Meaning |
|-------|---------|
| `appointments_list.total` | Complete COUNT for the active filter |
| `appointments_list.returned` | Rows in `todays_appointments` |
| `appointments_list.truncated` | `total > returned` |
| `appointments_list.limit` | Cap applied |

UI must show a partial-list banner when `truncated` is true. Never imply the detail table is complete when truncated.

Reception board (`reception_queue`) remains separately capped at 200 for the live board UI.

## Billing (complete aggregates)

No row caps. SQL aggregates in `location_outstanding_summary` / `location_payments_in_interval`.

Canonical per-invoice rule: `outstanding_for_invoice = grand_total − effective_allocated − issued credits` (never negative under allocation caps).

Aggregate mirrors that over `issued|partially_paid` only:

| Metric | Definition |
|--------|------------|
| `outstanding_invoice_count` | Count of invoices at location with status `issued` or `partially_paid` |
| `outstanding_amount` | `SUM(grand_total) − SUM(effective forward allocations) − SUM(issued credit amounts)` for those invoices. Draft / paid / voided excluded. Currency INR (quantize half-up). |
| `payments_today_count` | Payments at location with `received_at` in location service day; excludes `refunded` |
| `payments_today_amount` | Sum of those payment amounts |

Effective allocations = forward `payment_allocations` rows whose id is not referenced by any `reversal_of_id` (same rule as `effective_allocated`).

Refunded payments do not change AR unless allocation reversals run; reconcile tests cover refunds of unallocated payments and multi-allocation cases.

## Availability

| Field | Source |
|-------|--------|
| `clinic_hours` | `location_working_hours` for the service weekday |
| `practitioners` | Tenant-approved active practitioners |
| `staff_windows` | Optional `staff_schedules` when actor has `staff.manage` |

## Permissions

Dashboard requires `tenant.read` plus at least one of: `appointment.read`, `followup.read`, `billing.read`, `staff.manage`.

Sections omitted when the corresponding domain permission is missing.

### Navigation (P1.5)

Shell starts in **loading** with Home/Sessions only (`SAFE_NAV`), then replaces with permission-filtered NAV. On context failure: muted error + limited SAFE_NAV (APIs still enforce authz). `fetchWorkspaceContext` uses TTL cache + in-flight dedupe; `clearWorkspaceContextCache` for logout/tenant switch.

Portal-only routing unchanged.

### Home routing

- Portal-only users → `/portal` (unchanged).
- Staff with ops domain permissions → Home shows Operations deep-link CTA (no forced redirect).
- Staff without ops permissions → empty workspace notice.

## Known limitations

- Ops follow-up KPIs and Follow-ups workspace day bases differ by design (location vs UTC).
- Detail appointment table is intentionally partial above 50 rows (signaled via `appointments_list`).
- Reception board still uses a 200-row board cap (separate from ops metrics).
