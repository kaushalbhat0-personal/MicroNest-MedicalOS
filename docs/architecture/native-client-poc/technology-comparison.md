# Technology comparison (evidence-based)

## Android host

| Criterion | Capacitor + Vite SPA | Next static export / SSR wrap | Kotlin Compose native |
|-----------|----------------------|-------------------------------|------------------------|
| Routing compatibility | **Good** — client router | **Poor** — App Router / SSR / rewrites | Native |
| Auth integration | Bearer + secure plugin | Cookie / remote WebView fragile | Bearer |
| `@healthcare-os/ui` reuse | **High** (React 19) | High but couples Next | **Low** |
| Native plugins | Good ecosystem + custom bridges | Same host if Capacitor | First-class |
| Offline startup | Bundle in APK | Remote URL fails | Strong |
| Background sync | Needs WorkManager bridge | Weak if remote | WorkManager |
| Upgrade cost | Medium (Capacitor + Android Gradle) | High fighting Next | Highest UI cost |
| PoC evidence | SPA **build PASS**; APK **NOT IMPLEMENTED** | Rejected by constraint | Not built |

**Recommendation:** Capacitor + dedicated SPA. Do not wrap Next SSR.

## Windows host

| Criterion | Tauri 2 | Electron | .NET WinUI |
|-----------|---------|----------|------------|
| UI reuse | SPA + `@healthcare-os/ui` | Same | Rebuild |
| Packaging / signing | MSI/NSIS + Authenticode | NSIS/Squirrel + Authenticode | MSIX |
| Auto-update security | Signed updater | Code-signed releases | Store / MSIX |
| Local DB | Rust SQLCipher bridge | Node native / sidecar | Native |
| Key protection | DPAPI from Rust | Harder to isolate from renderer | DPAPI native |
| Resource usage | Smaller | Larger Chromium | Medium |
| Maintenance | Rust + web | Node + Chromium CVEs | C# team skill |
| PoC evidence | Shell **NOT IMPLEMENTED** (no Rust) | Not chosen | Not chosen |
| Crypto PoC | N/A | N/A | Python DPAPI **PASS** validates OS API |

**Recommendation:** Stay on Tauri 2 per A0; install Rust toolchain before shell spike. Electron only if Tauri bridge timeline slips.

## Local encryption

| Layer | Android target | Windows PoC proven | Production target |
|-------|----------------|--------------------|-------------------|
| DB engine | SQLCipher | AES-GCM sealed SQLite file | SQLCipher both |
| Key wrap | Android Keystore | DPAPI CurrentUser **PASS** | Platform `SecureKeyStore` |
| Equivalence | **Not equivalent** | **Not equivalent** | Shared interface only |

## Sync / shared

| Piece | Status |
|-------|--------|
| Server domain outbox | Exists — do not overload |
| Device outbox | Missing — see A3 |
| Offline clinical writes | Disabled this phase |

## Cost / complexity ranking (this evidence)

1. **Lowest near-term risk:** Finish Windows secure-store path (DPAPI proven) + backend native token + device contracts.  
2. **Medium:** Tauri shell once Rust available.  
3. **Blocked until lab:** Android Keystore + SQLCipher on emulator/device.  
4. **Highest if premature:** Full dual-client feature build in parallel.
