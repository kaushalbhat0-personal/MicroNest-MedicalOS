# Known limitations (A1 / A2 / A3 PoCs)

## Tooling / environment

| Limitation | Impact |
|------------|--------|
| No JDK / `javac` on PATH | Cannot compile Android Keystore sample or Capacitor Android project |
| No `adb` / no device or emulator evidence | A1 Keystore + SQLCipher **cannot PASS** |
| No `rustc` / `cargo` | Tauri 2 Windows shell **NOT IMPLEMENTED** |
| Android SDK present but incomplete for this PoC | Partial; not sufficient alone |

## What the PoCs are not

- Not production apps, stores, or signed releases
- Not connected to staging/production FastAPI for login (controlled mock only)
- Not SQLCipher engine proofs (Windows used AES-GCM file seal; Android had no DB)
- Not proof that Capacitor plugins work on device
- Not implementation of device/lease/sync APIs
- Not a change to web release reconciliation / P3.7D.4 work

## Security / product limitations to carry forward

1. **Revocation while permanently offline:** server revoke cannot reach the device; lease expiry is the hard stop; residual encrypted cache may remain until wipe/expiry UX.
2. **DPAPI profile binding:** another Windows user or broken profile cannot decrypt; re-enrollment required.
3. **Android Keystore variability:** hardware-backed vs software; must be verified per device class in lab.
4. **Production login cookies-only:** native Bearer bootstrap requires backend change (same session model).
5. **Backup:** sealed files can still be copied; encryption + wipe + clinic device policy required.
6. **Offline clinical writes:** deliberately disabled; enabling later needs conflict + audit completeness.
7. **Mock API ephemeral HMAC secret:** process-local; never use in any environment beyond PoC.

## Documentation honesty rules applied

- Source samples ≠ runtime PASS
- Model compile ≠ contract PASS
- CONDITIONAL PASS names the remaining blocker (Windows: Tauri/SQLCipher engine; not used to hide Android Keystore failure)
