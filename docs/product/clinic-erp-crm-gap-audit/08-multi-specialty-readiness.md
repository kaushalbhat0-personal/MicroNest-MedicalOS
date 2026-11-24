# 08 — Multi-specialty readiness

| Capability | Classification | Evidence |
|------------|----------------|----------|
| Typed specialty registry | **IMPLEMENTED AND VERIFIED** | `modules/workspaces/registry.py` — dental ready, ophthalmology discovery |
| Tenant specialty enablement | **IMPLEMENTED AND VERIFIED** | Workspace provision + `tenant_specialties` |
| Specialty read model | **IMPLEMENTED AND VERIFIED** | Tenant detail + platform console |
| Specialty-filtered navigation | **MISSING** | Static `apps/web/lib/nav.ts` |
| Clinical vs specialty boundaries | **IMPLEMENTED AND VERIFIED** | Generic clinical + dental pack; money separation |
| Dental pilot workflows | **IMPLEMENTED AND VERIFIED** | Dental API/UI/tests |
| Ophthalmology clinical | **BLOCKED BY EXTERNAL DECISION** | Discovery docs only; no invented workflows |
| Adding specialties without forking core | **IMPLEMENTED BUT NEEDS IMPROVEMENT** | Registry pattern works; nav/forms packs incomplete |

**Product rule:** Dental is pilot specialty, not the entire product identity. Do not activate ophthalmology clinical without sign-off.
