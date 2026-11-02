# P1-03 — Auth failures return 401 without raising

Date: 2026-11-02 · Status: accepted.

Context: login/refresh wrote security-audit rows (failed logins, reuse
detection, family revocation) in the request transaction, then raised
`AuthError`. The scoped-transaction rollback discarded the evidence — a
security-event loss bug (reuse detection revoked nothing).

Decision: `login` and `refresh` catch `AuthError` and return a 401 response
(`errors.unauthorized_response`) so the transaction commits and the
security writes persist. Business-domain errors still raise (atomicity kept).

Consequences: 401 paths are part of the happy-path transaction; reuse
detection provably revokes the family (test).
