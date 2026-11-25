# Known limitations (Phase 1.3)

1. Clinical modules are placeholders — not full patient/schedule/billing apps.  
2. Dashboard depends on operations feature entitlement + location; empty clinics show errors honestly.  
3. `HOS_M3_AUTOLOGIN_*` is for synthetic evidence only — disable in any shared build.  
4. Debug EXE / unsigned NSIS only — not production distribution.  
5. JWT `iss`/`aud` still deferred.  
6. Device cryptographic PoP still deferred.  
7. Inventory/staff attention on admin dashboard is nav/permission visibility, not live inventory KPIs beyond operations billing block.  
8. Manual multi-monitor UX polish and screenshot gallery not produced.  
9. Staging CORS not modified; Rust HTTP avoids the need for now.
