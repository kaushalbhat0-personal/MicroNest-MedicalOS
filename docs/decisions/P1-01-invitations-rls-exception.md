# P1-01 — Invitations table exempt from RLS

Date: 2026-11-02 · Status: accepted · Amends: P0.5 §19 (RLS everywhere),
locks 0005_rls pre-release.

Context: invite acceptance is a public, token-gated endpoint. No tenant
context exists before the token is presented, so an RLS policy on
`invitations` makes acceptance impossible without a bypass.

Decision: `invitations` is capability-gated, not tenant-gated:

- reads only by 256-bit token hash (single-use, 7-day expiry);
- no endpoint enumerates invitations (asserted by contract + isolation tests);
- the accept transaction scopes `app.tenant_id` to the invitation's own
  tenant (server-derived from the token lookup) before any membership write.

Consequences: token secrecy is load-bearing (delivered out-of-band by the
inviter); acceptance rate-limited in P5.
