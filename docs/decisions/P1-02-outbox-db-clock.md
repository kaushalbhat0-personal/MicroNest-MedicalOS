# P1-02 — Outbox claim clock evaluated in the database

Date: 2026-11-02 · Status: accepted.

Context: `claim_batch` compared `next_attempt_at` against a Python-side
`datetime.now()`. Under coarse timer granularity the Python clock can read
earlier than a DB `now()` taken moments before, so due rows were skipped
nondeterministically (found via the dead-letter test).

Decision: the due boundary uses `func.now()` (database statement timestamp).
App and DB host clocks are never compared across this boundary.

Consequences: worker correctness no longer depends on host clock agreement;
tests force due rows with a 1-second margin for determinism on any platform.
