# SQLCipher / encrypted SQLite on Android (A1)

## Intended production path

- `net.zetetic:android-database-sqlcipher` or community-maintained SQLCipher Android binding
- Passphrase / key bytes from `KeystoreDbKeyStore.unwrap()` — never from plaintext SharedPreferences
- `android:allowBackup="false"` + exclude DB paths in backup rules
- After logout: close DB, delete DB files, `KeystoreDbKeyStore.clear()`

## PoC status on this machine

| Item | Status |
|------|--------|
| Kotlin Keystore wrapper source | Implemented (sample) |
| SQLCipher dependency linked in APK | **NOT IMPLEMENTED** (no full Capacitor Android project build) |
| Emulator/device open+reopen encrypted DB | **NOT TESTED** |
| Keystore encrypt/decrypt round-trip | **NOT TESTED** (no JDK/device runtime evidence) |

Without the runtime rows above, A1 encrypted-DB + Keystore requirement is **FAIL / NOT TESTED**, not PASS.
