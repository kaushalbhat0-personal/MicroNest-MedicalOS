# Tauri desktop foundation

## Stack (verified on workstation)

| Component | Version |
|-----------|---------|
| Node | v24.11.1 |
| Rust | 1.100.0 (stable-x86_64-pc-windows-msvc) |
| Cargo | 1.100.0 |
| Tauri | 2.x (`tauri` crate 2.12.7 during build) |
| Vite | 6.4.6 |
| React | 19.0.0 (aligned with monorepo) |
| TypeScript | 5.7.2 |

## Layout

```
apps/desktop/
  src/                 # React shell (login, workspace, placeholder home)
  src-tauri/           # Rust host + DPAPI store
  dist/                # Vite production assets (built)
```

## Security configuration

| Control | Setting |
|---------|---------|
| Capabilities | `core:default` only — **opener plugin removed** |
| CSP | Restrictive default-src/connect-src in `tauri.conf.json` |
| IPC | Allowlisted commands: token store + API base + instance id |
| Navigation | No remote content loading for app shell |
| API | Direct HTTPS/HTTP to configured `HOS_API_BASE_URL` / `VITE_HOS_API_BASE_URL` — **not** via Vercel proxy |

## UI reuse

Uses `@healthcare-os/ui` (`Button`, `Field`, `Input`, `Card`, `Alert`, `EmptyState`, `ErrorState`, `LoadingState`) + `tokens.css` / `components.css`.

**Not imported (avoid Next / heavy clinical surfaces):** Next.js modules, full `AppShell` clinic nav with Next links, WhatsApp actions, imaging viewer (deferred).

## Commands

```powershell
cd apps/desktop
npm run build          # Vite SPA → dist/
cargo test --manifest-path src-tauri/Cargo.toml
npx tauri build        # EXE/NSIS when WebView2 + bundler deps present
$env:HOS_API_BASE_URL="http://127.0.0.1:8000"; npx tauri dev
```

## Runtime status

See `test-evidence.md` for whether `tauri build` / `tauri dev` completed on this machine.
