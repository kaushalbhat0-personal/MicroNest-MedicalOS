# Outbox Model (P1)

`outbox_events(id, occurred_at, type, tenant_id?, aggregate(+id), payload,
status, attempts, next_attempt_at, last_error)`.

- `emit()` runs inside the caller's transaction (atomic publish).
- `claim_batch` uses `SELECT … FOR UPDATE SKIP LOCKED` with the due boundary
  evaluated in the DATABASE (`func.now()`): app/DB clock skew must never
  decide claim eligibility (fixed during P1, see decisions).
- `process_batch` dispatches to handlers, bounded backoff, MAX 8 attempts,
  then DEAD (poison events never block the queue; dead-letter is alertable).
- Payloads carry references only (`assert_port_safe` rejects clinical/secret keys).
- Worker: `python -m app.platform.events.worker` (poll + dispatch; P1 handler:
  dev notification adapter).
