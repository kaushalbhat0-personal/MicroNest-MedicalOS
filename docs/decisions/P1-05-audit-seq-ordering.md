# P1-05 — Audit chain ordered by identity sequence, not (timestamp, id)

Date: 2026-11-02 · Status: accepted · Migration: 0006_audit_seq.

Context: the chain linked/verifed in (occurred_at, id) order. UUIDv7 ids
carry random bits (not monotonic within a timestamp) and `occurred_at` can
tie under coarse clocks, so rapid appends linked nondeterministically —
caught as an intermittent `verify_chain` failure.

Decision: `audit_events.seq BIGINT GENERATED ALWAYS AS IDENTITY` is the
order key for linkage (`seq desc` latest) and verification (`seq` asc).
Timestamps remain evidence, not order.

Consequences: rollback-consumed identity values may leave gaps — verification
checks linkage, not gaplessness. Same-timestamp bursts are now deterministic.
