# Financial Reconciliation

## Clinic AR

**No clinic reconciliation HTTP API.** Backend has service-level aggregate checks (`test_outstanding_aggregate_reconcile.py`).

Desktop M8 provides:
- Per-invoice balance endpoint display
- Ops dashboard outstanding aggregate (existing Dashboard, when permitted)
- Dues list from invoice outstanding fields

**Does not** auto-repair discrepancies or invent a reconciliation algorithm.

## SaaS platform reconcile

`POST /api/v1/platform/saas/reconcile/{tenant_id}` is unrelated to clinic billing and out of scope.
