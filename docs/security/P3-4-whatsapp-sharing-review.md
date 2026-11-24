# P3.4 — WhatsApp sharing security review

**HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**Verdict:** **OK for synthetic / assisted pilots** with documented limits.

## Controls

| Control | Status | Notes |
|---------|--------|-------|
| Tokens only from backend | OK | Invite `token` from `POST /invites`; portal has no enrollment secret |
| One-time / expiry | OK | Invite accept + revoke unchanged; UI warns single-use |
| No token logging | OK | Success alerts no longer dump raw `/invite?token=` into the message string; share state holds link for UI only |
| No PHI in templates | OK | Staff/portal templates: clinic name, email, URLs only |
| Permission for underlying action | OK | Invites still require invite APIs; portal enroll `staff.manage`; care WA `communication.read` + consent |
| Tenant scoping | OK | All create calls use `X-Tenant` + existing `match_tenant` |
| No insecure IDs in links | OK | Invite uses opaque token; portal share uses public paths only |
| No WA Business / scraping | OK | `wa.me` open only |
| Auto-send claim | OK | UI Alert + checkbox; `auto_send=false` on patient API |

## Patient care path

`resolveOpenUrl` → `POST /whatsapp-link` with `require_consent=true`. Server validates purpose, patient phone, consent. Client may prefill message ≤500 chars (server schema). Opening is not logged as contacted until staff confirm dialog (existing behavior).

## Residual risks

| Risk | Mitigation / defer |
|------|---------------------|
| Staff can still screenshot or forward invite link | Operational; expiry + revoke |
| Portal share uses generic password-reset (no bound token) | Matches API; attacker still needs email + reset flow throttles |
| Clipboard may retain invite URL | Short-lived UI state; facilitator guidance |
| P3.0 `storage_key` / dental consent | Unrelated; still open for real PHI |

## Not claimed

Automated WhatsApp delivery, production email, or real-patient-data readiness.
