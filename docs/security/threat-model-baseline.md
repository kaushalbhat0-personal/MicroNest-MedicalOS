# Threat-Model Baseline (P1)

Covered by tests where noted; the rest is P7/P8 hardening.

| Threat | P1 mitigation | Test |
|---|---|---|
| Tenant breakout (missing filter) | server-derived scope + RLS fail-closed | isolation + RLS suites |
| BOLA/IDOR | ownership check + 404-no-oracle | isolation suite |
| Stolen session | 10-min access, rotating refresh, reuse→family revoke | auth flow tests |
| Credential stuffing | per-IP + per-account throttle, generic errors | rate-limit behavior |
| Privilege escalation | permission catalog, deny-by-default, last-admin guard | isolation suite |
| Audit tampering | append-only + hash chain | audit tests |
| Log/PHI leakage | scrubbing filter + port guards + no-body logging | scrub + logging tests |
| Secret leakage | no committed secrets, hygiene gate | repo hygiene tests |
| Fake guards | verification enforced (no no-ops), dev adapters fail-closed | review + constructor tests |
| Migrate-at-boot | no startup migration (tested) | deployment test |

Deferred: MFA/WebAuthn (P5), Redis-backed limits (P7), WAF/SAST, pentest (P8),
supply-chain SBOM (P7), backup/restore drills (P7/P8).
