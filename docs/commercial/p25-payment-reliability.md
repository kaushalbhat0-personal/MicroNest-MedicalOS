# P2.5 — Payment Reliability & Production Readiness

**Baseline HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**Migration:** `0027_saas_payment_reliability` (after `0026_saas_payments`)  
**Builds on:** `docs/commercial/p24-payment-provider-integration.md`

## Audit findings (from P2.4)

| Gap | Fix in P2.5 |
|-----|-------------|
| Sync webhook re-raise rolled back inbox on business failure | Durable inbox; verified receipts survive processing failure |
| Full refund auto-cancelled subscription | Refund updates **transaction** only; subscription unchanged |
| No retry / admin inspection | `retryable_failure` / `permanent_failure` + platform replay |
| No cancel-at-period-end | `subscriptions.cancel_at_period_end` |
| Production could theoretically use mock | Boot validation fail-closed |
| No secret rotation | Current + previous webhook HMAC secrets |
| Auto-renew implied | Explicit manual renewal UI + `purpose=renewal` |

## Durable inbox lifecycle

Statuses: `received` → `verified` → `pending` → `processing` → `processed`  
Failure paths: `retryable_failure` | `permanent_failure` | `ignored` | `duplicate`

1. Verify HMAC on **raw body** (current or previous secret). Invalid → **403**, no durable row.
2. Persist unique `(provider, provider_event_id)` as `pending` with safe `event_refs` (order/payment ids, amounts only — **no full card/PHI payload**).
3. Process in-request; on success → `processed`.
4. On transient error → `retryable_failure` + `next_attempt_at` (outbox-style backoff).
5. On conflict/validation/exhausted attempts → `permanent_failure`.
6. HTTP **200** after verified receipt (including failures) so providers stop retry storms.
7. Concurrent claim: `FOR UPDATE SKIP LOCKED` in `process_due_webhooks`.

## Retry strategy

- Backoff: same schedule as platform outbox (`backoff_for_attempt`).
- Max attempts: `SAAS_WEBHOOK_MAX_ATTEMPTS` (default 8).
- Platform: `POST /api/v1/platform/saas/webhooks/process-due`
- Replay: `POST /api/v1/platform/saas/webhook-inbox/{id}/replay`
- Inspect: `GET /api/v1/platform/saas/webhook-inbox?status=`
- Operators **cannot** mark an unverified payment as paid.

## Refund / dispute mapping

| Event | Transaction | Subscription |
|-------|-------------|--------------|
| `refund.processed` (partial) | `partially_refunded`, accumulate `refunded_amount_minor` | **unchanged** |
| `refund.processed` (full) | `refunded` | **unchanged** (paid-through period stands until explicit cancel) |
| `payment.dispute.*` | `disputed` | **unchanged** |
| Duplicate capture | no-op if already `paid` | — |

Explicit owner/platform cancel remains the only path to end entitlement early.

## Renewal / cancellation

- **No provider-managed recurring debit** in this release.
- Manual renewal: checkout with `purpose=renewal` (extends period from current `period_end` when still valid).
- Cancel now → validated `cancelled` transition.
- Cancel at period end → `cancel_at_period_end=true`; access continues until `period_end`.
- Reactivation of `cancelled` is not via payment webhook (conflict); use authorized assign flows.

## Reconciliation

`POST /api/v1/platform/saas/reconcile/{tenant_id}`:

- Calls `fetch_payment_status` when `provider_payment_id` present.
- Detects amount/currency mismatch, unconfirmed capture, pending-vs-captured heal, delinquent-with-paid heal, stale pending, open inbox.
- Idempotent, tenant-scoped via `set_config`, platform-admin only.

## Secret / environment security

- Production: `SAAS_PAYMENT_PROVIDER=razorpay` required; mock forbidden; live keys required; test keys rejected.
- Non-prod razorpay: `rzp_test_*` required.
- Webhook rotation: `SAAS_PAYMENT_WEBHOOK_SECRET` + `*_PREVIOUS` (and Razorpay equivalents).
- Never log/return secrets; exception redaction strips key material.
- Frontend receives public key id only.

## Sandbox verification

**Status: BLOCKED in this environment** — no `RAZORPAY_*` test credentials in `.env`.

Manual steps when credentials are available:

1. Set `SAAS_PAYMENT_PROVIDER=razorpay`, `RAZORPAY_KEY_ID=rzp_test_…`, secrets.
2. Create checkout for a trial tenant; confirm order amount/currency in Razorpay dashboard.
3. Pay with Razorpay test card; confirm webhook `payment.captured` with valid signature.
4. Replay same event → `duplicate`.
5. Send invalid signature → 403.
6. Partial refund in dashboard → internal `partially_refunded`, subscription still active.
7. Run platform reconcile; confirm findings empty or healed.

Do **not** treat MockProvider tests as live sandbox evidence.

## Production deployment requirements

- `ENV=production`, `SAAS_PAYMENT_PROVIDER=razorpay`, live keys + webhook secret.
- Public webhook URL: `/api/v1/webhooks/saas/razorpay`
- Cron/ops: periodically `process-due` for retryable inbox rows.
- Separate clinic AR vs SaaS payment dashboards.

## Manual recovery playbook

1. Inspect inbox (`permanent_failure` / `retryable_failure`).
2. Fix root cause (plan mismatch, missing actor, etc.).
3. Replay inbox row **or** re-deliver provider webhook (idempotent).
4. Reconcile tenant.
5. Never set `tenants.status` for billing; never invent a paid txn without provider evidence.

## Known limitations

- Live Razorpay sandbox not verified in CI/this machine.
- Razorpay Subscriptions auto-debit still deferred.
- Chargeback lifecycle beyond `payment.dispute.*` marking is manual.
- Raw webhook body not retained (digest + `event_refs` only).

## P2.6 readiness

Live sandbox soak, provider subscription auto-renew mapping, dispute win/loss playbooks, alerting on `permanent_failure` count.
