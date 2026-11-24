# P2.4 — Payment Provider Integration & Subscription Lifecycle

**Baseline HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**Migration:** `0026_saas_payments`  
**Module:** `backend/app/modules/saas_payments/`

## Provider selection

| Option | Fit |
|--------|-----|
| **Razorpay** | Selected — INR catalog, India market, Orders + payment webhooks |
| Stripe | Viable later; not required for INR-first |
| Existing code | **None** — only `provider_ref` column reserved; clinic AR `provider_ref` is unrelated |

Adapter: `provider.py` (`MockProvider` for tests/local, `RazorpayProvider` when configured). Subscription domain never imports Razorpay payloads.

## Payment domain boundary

| Ledger | Tables | Owners |
|--------|--------|--------|
| SaaS clinic subscription | `saas_customers`, `saas_payment_transactions`, `saas_webhook_inbox` | Tenant subscription |
| Clinic→patient AR | `payments`, `invoices`, … | Patient care billing |

No FKs between the two. Amounts snapshotted from `subscription_plans.price_minor` at checkout.

## Checkout flow

1. Owner/tenant-admin `POST …/subscription/checkout` with `plan_code` + `idempotency_key`.
2. Server resolves plan, snapshots amount/currency, creates provider order.
3. Returns `order_id` + public key only (no secrets).
4. **Browser return URL is informational** — never activates subscription.

## Webhook verification & idempotency

- `POST /api/v1/webhooks/saas/{provider}`
- HMAC-SHA256 over **raw body** (`X-Razorpay-Signature` or `X-SaaS-Signature` for mock).
- Insert `saas_webhook_inbox` unique `(provider, provider_event_id)`.
- Duplicate deliveries → `status=duplicate` / already `processed`.
- Resolve txn by `provider_order_id`; set `app.tenant_id` before writes.
- Stale `payment.failed` cannot overwrite `paid`.

## State-transition mapping

| Provider event | Internal effect |
|----------------|-----------------|
| `payment.captured` | Txn→paid; `assign_plan` / `transition_status` → `active` via subscriptions service |
| `payment.failed` (from active) | Txn→failed; `past_due` then `grace` (grace days configurable) |
| `refund.processed` | Txn→refunded; cancel if active |

Never mutates `tenants.status`.

## Renewal / dunning

- Period stored on txn + subscription `period_start`/`period_end`.
- Failed renewal → past_due → grace (`SAAS_GRACE_DAYS`, default 7).
- Late successful payment heals to active (webhook or reconcile).
- Owner cancel → validated `cancelled` transition.

Provider-managed Razorpay Subscriptions API is **not** required for MVP; Orders + capture webhooks cover initial paid activation. Recurring provider subscriptions can map later.

## Reconciliation

`POST /api/v1/platform/saas/reconcile/{tenant_id}` (platform admin):

- Detects active-without-paid, delinquent-with-paid (heals), stale pending.
- Idempotent / retry-safe.

## Security & secrets

- Secrets only in env (`RAZORPAY_*`, `SAAS_PAYMENT_WEBHOOK_SECRET`).
- Never returned in API JSON or structured logs.
- Mock default for local/tests.
- Portal access during commercial delinquency unchanged (P2.3).

## Sandbox testing

Set `SAAS_PAYMENT_PROVIDER=mock`. Tests sign bodies with `SAAS_PAYMENT_WEBHOOK_SECRET`.

## Manual recovery

1. Platform reconcile tenant.
2. If provider shows captured but inbox failed, re-deliver webhook (idempotent).
3. Do not manually set `tenants.status` for billing.

## Known limitations

- No live Razorpay network in CI (mock).
- No Razorpay Subscriptions auto-debit yet (Orders MVP).
- Chargebacks mapped only if provider emits refund-like events.
- `subscription_detail.provider_ref` still omitted from API for safety (customer id stored server-side).

## P2.5 readiness

Receipting UX polish, provider subscription auto-renew mapping, chargeback playbooks, production secret rotation.
