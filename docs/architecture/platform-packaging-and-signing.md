# Platform Packaging and Signing

**Phase:** A0 — architecture / feasibility (no APK/EXE produced)  
**Date:** 2026-11-25

## 1. Purpose

Define how Web, Android, and Windows artifacts are built, signed, distributed, and revoked — without mixing secrets into the application repository.

## 2. Web (existing)

| Item | Current / target |
| --- | --- |
| Build | Next.js on Vercel (`apps/web`) |
| Auth packaging | Same-origin `/api` rewrite (P3.7D); cookies Lax/HttpOnly/Secure |
| Secrets | Vercel Preview/Production env scopes; no JWT in `NEXT_PUBLIC_*` |
| Distribution | HTTPS Preview/Production URLs |

Web is **not** replaced by native packaging; it remains the primary online client.

## 3. Android APK / AAB

### 3.1 Artifacts

| Artifact | Use |
| --- | --- |
| AAB | Play Store upload (preferred) |
| APK | Sideload / enterprise MDM only when required |

### 3.2 Signing

| Key | Storage | Rules |
| --- | --- | --- |
| Upload key | CI secret store / hardware token | Never commit; rotate with Play Console |
| App signing key | Play App Signing (Google-held) | Prefer Play-managed |
| Debug key | Local only | Not for staging PHI builds |

### 3.3 Build pipeline (future)

1. Build SPA assets.  
2. `cap sync android`.  
3. Gradle release assemble with minify.  
4. Sign → upload to Play internal testing / MDM.  
5. Map versionCode to git tag + backend min-version.

### 3.4 Runtime protections

- R8/ProGuard; strip logging of identifiers.  
- Disable backup for PHI DB (`android:allowBackup="false"`) or encrypt backups.  
- Network security config: cleartext blocked.  
- Optional SafetyNet/Play Integrity for device attestation (privacy review required).

## 4. Windows EXE installer

### 4.1 Artifacts

| Artifact | Use |
| --- | --- |
| Signed EXE/MSI bootstrapper | Clinic IT install |
| MSIX (later) | Store / cleaner updates |

### 4.2 Signing

| Item | Requirement |
| --- | --- |
| Certificate | Org Authenticode (OV/EV); EV preferred for SmartScreen reputation |
| Timestamping | RFC 3161 timestamp so signatures survive cert expiry |
| CI | Sign in locked runner; cert not in git |
| Updater | Manifest + package signatures verified before apply |

### 4.3 Install layout

```
%LOCALAPPDATA%\HealthcareOS\
  app\           # binaries
  data\          # encrypted SQLite (ACLs: current user)
  logs\          # no PHI
```

Per-user install avoids admin elevation for routine use.

### 4.4 Auto-update

- Separate staging and production update channels.  
- Fail closed on signature/channel mismatch.  
- Do not download EXE over HTTP.

## 5. Shared release discipline

| Rule | Rationale |
| --- | --- |
| No signing keys in git | Matches existing secret-handling culture |
| Version triple: `marketing` / `native build` / `min API` | Block obsolete clients that skip authz leases |
| SBOM + dependency scan on native builds | Supply chain |
| Crash reporters scrub identifiers | Threat model: untrusted clients, high-value PHI |
| Device revoke list on API | Compromised laptop/phone |

## 6. Distribution matrix

| Channel | Web | Android | Windows |
| --- | --- | --- | --- |
| Public SaaS | Vercel | Play production | Signed download portal |
| Staging | Vercel Preview | Play internal / MDM | Staging feed |
| Air-gapped clinic | N/A / private host | MDM APK | Offline installer + manual update |

## 7. Prerequisites before first signed build

1. Legal entity + signing certificates procured.  
2. CI secret backend chosen.  
3. Privacy policy covers on-device PHI cache.  
4. `min_client_version` enforced by API.  
5. SPA shell + Bearer device auth shipped.

## 8. Packaging readiness verdict

| Platform | Ready to produce signed artifact in A0? |
| --- | --- |
| Web | **Yes** (already) |
| Android APK/AAB | **No** — packaging design only |
| Windows EXE | **No** — packaging design only |
