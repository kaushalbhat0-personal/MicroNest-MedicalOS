# Runtime test evidence

## Toolchain

| Tool | Version |
|------|---------|
| Node | v24.11.1 |
| rustc/cargo | 1.100.0 |
| Vite | 6.4.6 |
| Tauri | 2.12.x |
| Python | 3.10.11 |

## Commands

```powershell
# Unit
cd apps/desktop; npm run test:unit   # 6 passed
npm run build

# Backend regression
python -m pytest tests/api/test_native_auth.py tests/api/test_auth_flow.py -q  # 17 passed

# Migrate + API
alembic -c backend/alembic.ini upgrade head
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000

# Seed synthetic user
python scripts/_p13_seed_desktop_user.py

# Rebuild + run EXE evidence
cd apps/desktop; npx tauri build --debug
$env:HOS_API_BASE_URL="http://127.0.0.1:8000"
$env:HOS_M3_AUTOLOGIN_EMAIL="desktop.poc@example.com"
$env:HOS_M3_AUTOLOGIN_PASSWORD="Desktop-PoC-Only-99zz"
Start-Process .\src-tauri\target\debug\healthcare-os-desktop.exe
# Evidence written to %LOCALAPPDATA%\HealthcareOS\evidence\m3_runtime_evidence.json
```

## Results matrix

| Test | Status |
|------|--------|
| Desktop nav unit tests | **PASS** (6) |
| Vite build | **PASS** |
| Native+browser pytest | **PASS** (17) |
| Alembic 0028 on local DB | **PASS** |
| Native login HTTP smoke | **PASS** |
| EXE M3 autologin evidence | **PASS** |
| DPAPI file after login | **PASS** (envelope, no plaintext token) |
| Refresh rotate + /me | **PASS** |
| Logout clears DPAPI | **PASS** |
| Manual keyboard screenshot gallery | **NOT TESTED** (evidence via in-app checklist) |

## Artifact paths

- EXE: `apps/desktop/src-tauri/target/debug/healthcare-os-desktop.exe`  
- Evidence copy: `docs/architecture/desktop-client/phase-1-3/evidence/m3_runtime_evidence.json`
