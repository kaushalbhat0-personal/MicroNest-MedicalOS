# Logging & Data-Handling Rules (P1, engineering rulebook v0)

- Three streams: app logs (JSON-ish, request_id), security audit
  (`auth_events`), business audit (`audit_events`). No PHI in any of them.
- `ScrubbingFilter` on every app logger + root: redacts SENSITIVE_KEYS
  (passwords, tokens, OTPs, secrets, clinical keys) and JWT shapes in free text.
- Ports reject forbidden keys (`assert_port_safe`); outbox payloads are refs.
- Web: no tokens in localStorage/sessionStorage (hygiene test scans `apps/`).
- Classification table (P0.5 §21) applies from P2 data onward; P1 stores no
  clinical payloads at all (identity/tenancy/audit metadata only).
