# Implementation roadmap (post-PoC)

**Do not begin full application development in this phase.** Sequence below is the recommended next work after explicit approval.

## Decision: do not build both full clients now

Evidence does **not** justify parallel full Android + Windows product builds.

| Order | Workstream | Why first |
|-------|------------|-----------|
| 1 | Backend native auth + device/lease contracts (A3 implement) | Both clients blocked on token issuance & revoke |
| 2 | Windows Tauri shell + SQLCipher behind proven DPAPI abstraction | Crypto OS path already **PASS**; Rust toolchain is the gate |
| 3 | Android lab: JDK + emulator Keystore/SQLCipher harness | Acceptance still **FAIL** without runtime |
| 4 | Shared SPA package consuming `@healthcare-os/ui` + api-client | After auth contracts stable |
| 5 | Offline **read** sync (assigned patients / 7-day appointments) | Writes remain offline-off |
| 6 | Packaging/signing/auto-update | After functional shells |
| 7 | Android clinic MVP (read-mostly) | Only after Keystore evidence PASS |
| 8 | Offline clinical writes | Separate phase with conflict/audit complete |

## Phase gates (must PASS to proceed)

| Gate | Exit criteria |
|------|---------------|
| B0 Backend native session | Login/refresh JSON tokens for device-bound sessions; web cookies unchanged; tests |
| B1 Device registry | Register/revoke + session.device_id; audit events |
| B2 Lease | Issue/validate lease; configurable offline window; deny after expiry |
| W1 Tauri hello | Window loads SPA; no PHI |
| W2 SQLCipher + DPAPI | Runtime evidence JSON equivalent to A2 PoC using SQLCipher |
| A-lab | Emulator evidence: Keystore wrap + SQLCipher open/reopen |
| S1 Sync pull | Assigned patients + upcoming appointments only; synthetic fixtures in staging |

## Explicit non-goals until later

- Dual full UI parity with `apps/web`
- Offline clinical writes
- Automatic WhatsApp
- Subscription/payment changes
- Replacing Next.js web app

## Exact next phase recommendation

**Next phase = B0 + B1 (backend native token + device identity) in a dedicated branch, plus install Rust and scaffold Tauri hello — not Android product UI.**

Android remains a **lab spike** until Keystore/SQLCipher runtime PASS on a properly tooled machine.
