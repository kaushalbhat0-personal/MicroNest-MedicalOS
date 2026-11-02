# Module Boundaries & Dependency Rules (P1, locked)

Allowed direction (P0.5 §4, implemented):

```
api → {identity, tenancy, clinics, audit, notifications} services
tenancy → identity (users, practitioners) — never the reverse
clinics → tenancy (tenant validity)
audit → nothing (sink)
notifications → outbox only
platform/* → nothing above (bottom of the stack)
P2+ stubs → must not be imported by P1 code (contract test asserts absence)
```

Rules:

- Services own their tables. No cross-module queries; pass IDs, re-read in owner.
- No cross-aggregate JOIN writes. Cross-aggregate effects go via outbox events.
- Permissions: `platform/authz/permissions.py` is the ONLY catalog. Role names
  are bundles; `if role == "..."` outside seed/test code is a defect.
- Ports (`platform/ports`) are implemented by `platform/adapters` (dev) and
  `infrastructure/*` (later). Business logic branches on nothing deployment-specific.
