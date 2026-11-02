# Product Scope — P1 Platform Skeleton

P1 delivers the secure foundation and the minimal admin workflow:

platform admin → tenant → location → admin membership → login (cookies) →
invite → accept → membership + role → permission gates → audit → logout →
revocation. Cross-tenant attempts fail closed; sessions rotate with
reuse detection; audit is append-only and hash-chained.

Explicitly NOT in P1: scheduling, encounters, clinical, dental, billing,
payments, portal, subscriptions, licensing, deployment bundles, ABDM,
gateways, production notification providers, reporting, inventory.
Interfaces/ports exist where P2+ needs them; domains do not.
