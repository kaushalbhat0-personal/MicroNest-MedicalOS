# P2-01 Scheduling Domain Model (implementation decision record)

Date: 2026-11-02 · Status: implemented, awaiting architecture review + commit.

## Model

- `patients` (new module, tenant-owned): `id / tenant_id→tenants CASCADE /
  display_name / phone? / is_active / timestamps`. Identity only — no
  clinical fields, no demographics duplication. Referenced by appointments
  (`RESTRICT`: history never vanishes under a booking).
- `appointments` (scheduling module, tenant-owned): `id / tenant_id CASCADE /
  patient_id, practitioner_id, location_id RESTRICT / start_at, end_at
  (timestamptz, UTC) / timezone (IANA interpretation context) /
  status (native PG enum `appointment_status`) / notes (operational, ≤500) /
  idempotency_key? (+ partial unique `(tenant_id, key)`) /
  cancelled_at, cancelled_by, cancel_reason? / created_by / timestamps` +
  `ck_appointments_end_after_start`.
- Practitioner reuse: `practitioners` stays global; per-tenant attachment is
  the existing `practitioner_verifications` row. Booking requires an
  **approved** verification in the tenant (no theater). A practitioner working
  across locations needs no duplicate record — location lives on the booking.
- No rooms/chairs/shifts/rosters in P2 (explicitly deferred; a
  location-level exclusion would forbid legitimate parallel bookings).

## Lifecycle (single source: `TRANSITIONS` in `scheduling/service.py`)

`scheduled → {confirmed, checked_in, cancelled, no_show}` ·
`confirmed → {checked_in, cancelled, no_show}` ·
`checked_in → {completed, cancelled}` · terminal: `completed, cancelled,
no_show`. Same-state requests are no-op successes (retry-safe). Only
`scheduled/confirmed` may reschedule. Cancel records actor + timestamp +
optional short reason.

## Double-booking

Transaction-scoped advisory lock per practitioner
(`pg_advisory_xact_lock(hashtext('sched:' || practitioner))`) + overlap
predicate (`tstzrange &&`) over live statuses, excluding self on reschedule.
Chosen over range-exclusion constraints because `btree_gist` is not
guaranteed on every deployment target (verified absent in the local engine);
the service check is the friendly 409, the lock is the race guarantee.
Scope is practitioner-only by product rule (location exclusion deferred
with rooms).

## Timezone

Persist UTC instants; interpret wall-clock input in the **location's**
timezone (explicit `timezone` field may override). Aware input accepted as
instants; naive input is wall-clock (`fold=0`, documented). Non-existent
DST-gap times rejected (round-trip check); `ZoneInfo` names validated (no
server-local fallback). Response carries UTC instants + the zone name;
display conversion is a presentation concern (frontend `toLocaleString`).

List filters note: naive `start_from`/`start_to` bounds are interpreted as
UTC (tenant-wide filters have no single location context), while naive
booking input is interpreted in the location's timezone. Aware datetimes
are instants in both paths.

## Idempotency

Per-resource `idempotency_key` + partial unique index (no new mechanism —
there is no platform idempotency infra in P1). Replay with identical intent
returns the row; same key with different intent is 409. Cancel/status
retries are no-op successes via the same-state rule. Header
`Idempotency-Key` takes precedence over the body field.

## Authorization

`require(P.APPOINTMENT_*)` / `require(P.PATIENT_*)` on every route +
`match_tenant` 404-oracle + `ctx.location_ids` enforced in the service.
Seed bundles grew (migration 0007 data update): tenant_admin +all six;
doctor read/update + patient read; receptionist all incl. patient create;
nurse read. `SCHEDULE_MANAGE`/`QUEUE_MANAGE` stay declared-only (no
enforcement points yet).

## Audit / events

`appointment.create/reschedule/status/cancel` + `patient.register` appended
to the existing hash-chained stream (refs only; notes/phones/reasons with
free text never enter audit — reason allow-list test defers to P3 per P1.1).
No new domain event types: create-time confirmation reuses the existing
`notification.requested` outbox flow (SMS when the patient has a phone),
dispatched by the existing worker handler. Zero new queues, zero handlers.

## Migration

`0007_scheduling`: `appointment_status` enum + 2 tables + deferred P1 FK
index set (P1.1 list) + seed-bundle data update + grants + RLS
(`FORCE`, tenant-isolated) on both tables. Forward-only; downgrade restores
P1 seed bundles and drops cleanly (covered by the fresh-apply/rollback test).
