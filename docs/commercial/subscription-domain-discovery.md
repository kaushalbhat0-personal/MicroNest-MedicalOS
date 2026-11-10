# Subscription Domain Discovery

Status: discovery ONLY. No tables, routes, or payment code in this slice.
Companion: `docs/commercial/customer-onboarding-architecture.md`.

## 1. Current state

Nothing exists. `subscriptions/__init__.py` ("Plans, entitlements, usage."),
`licensing/__init__.py` ("Deployments, licenses, offline grace (reads never locked)."),
`branding/__init__.py` ("Branding resolution, templates, domains.") — one line each, no models or routes.
`support.grant` permission is defined; the granting flow is deferred to P5+.

## 2. Subscription lifecycle (proposed)

States: `trial → active → past_due → grace → suspended → cancelled`, plus `expired` for non-renewed terms.
Transitions are server-side only, driven by payment events (webhook, authenticated) or platform-admin action —
never by browser parameters. Every transition appends an audit event (refs only).

- `trial`: full operating capability with trial limits (seats/locations/SMS quota, time-boxed). No card required (D9).
- `active`: payment current. All entitled operations allowed.
- `past_due`: payment failed, within retry window. Fully operational; dunning notifications (post-P8.1C).
- `grace`: payment still unresolved after retries. Operational with visible banner; new staff invites and new portal enrollments blocked (proposed); clinical reads/writes continue (clinical-safety rule).
- `suspended`: grace exhausted. Writes blocked across the tenant (appointments, clinical, billing, invites, enrollments); **reads preserved** — clinical reads, portal reads, and audit reads are never locked by commercial state. Export remains available.
- `cancelled`/`expired`: same access posture as suspended plus data-retention clock (D4). Reactivation restores the same tenant and data; nothing is deleted by cancellation.

Downgrade/upgrade: plan change is effective at period boundary (proposed) with proration (D6); entitlement reduction never destroys data, it blocks new creation (e.g. locations beyond limit stay, new ones refused).

## 3. Entitlement model (proposed)

Entitlements are evaluated server-side per request from the subscription row, never from client claims:

- `max_locations`, `max_practitioners`, `max_staff_seats` (memberships counted by active role).
- `specialties_enabled` (relational set, e.g. dental/ophthalmology — never a JSON blob on the tenant).
- `portal_enabled` (boolean; reads preserved regardless per §2, governs new enrollments).
- `sms_quota`, `storage_quota` (counters with outbox-backed metering, fail-closed on exhaustion for sends only).
- `branding_custom` (boolean gate on the future branding resolver).
- Enforcement points: provision/add/create paths check the specific entitlement and raise a commercial 402/403 (new `subscription` error shape, no clinical detail); list/read paths are never gated.

## 4. Platform billing separation

New tables under a `subscription_*` namespace: `subscription_plans` (seeded by migration, versioned rows — never edited in place), `subscriptions` (tenant link, plan version, status, period bounds), `subscription_invoices`, `subscription_payments` (provider refs only, amounts via the existing `Money` pure functions — Decimal/INR discipline reused, tables never shared with clinic billing).

Invariants: clinic billing tables never gain a subscription foreign key; subscription tables never gain patient/clinical keys; the two ledgers reconcile by tenant id only. Payment collection (gateway, webhooks, signature verification, idempotency, receipting) is O4; this slice designs the tables and state machine only. No gateway credentials, no test-mode charges, no webhook endpoints in discovery.

## 5. Deployment licensing vs SaaS subscription

Separate axes by design (P7-01): a deployment license governs *where and how* the software runs (cloud/private/on-prem, offline grace with reads never locked); a SaaS subscription governs *which commercial entitlements* a clinic has on the hosted platform. On-prem installations do not consume SaaS subscriptions; SaaS tenants do not need deployment licenses. Enforcement code must branch on neither — adapter/selection pattern as with storage/notify.

## 6. Decisions requiring approval

D6 plan contents and limits; D9 trial terms (duration, card, limits); proration and period-boundary policy; dunning schedule and notification content; gateway selection (test then production); invoice/receipt format and tax treatment (works with the existing FY doc-number pattern or a parallel subscription sequence — recommend parallel sequence, pending approval); refund policy (D10); data-retention clock values (D4).
