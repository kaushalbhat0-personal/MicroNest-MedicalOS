# Multi-platform client architecture (A0)

Architecture and feasibility only — **no APK/EXE builds** in this phase.

| Document | Description |
| --- | --- |
| [cross-platform-client-architecture.md](./cross-platform-client-architecture.md) | Shared contracts, repo evidence, **final readiness verdict** |
| [android-client-architecture.md](./android-client-architecture.md) | Capacitor vs native, Keystore, SQLCipher, WorkManager |
| [windows-desktop-architecture.md](./windows-desktop-architecture.md) | Tauri 2 vs Electron, DPAPI, updater |
| [cross-platform-sync-design.md](./cross-platform-sync-design.md) | Local outbox, leases, conflicts, sync protocol |
| [platform-packaging-and-signing.md](./platform-packaging-and-signing.md) | APK/AAB and EXE signing / distribution |

## Verdict snapshot

| Track | A0 readiness |
| --- | --- |
| Android APK | **NOT READY** (architecture CONDITIONAL) |
| Windows EXE | **NOT READY** (architecture CONDITIONAL) |
| Shared sync implementation | **NOT READY** (design CONDITIONAL) |
