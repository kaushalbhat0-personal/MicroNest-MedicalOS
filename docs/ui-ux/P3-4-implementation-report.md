# P3.4 — Implementation report

**Verdict:** **PASS** (WhatsApp-assisted onboarding share — click-to-chat only)  
**HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3` (no commit)  
**Payments / Docker / specialty features:** untouched

## What shipped

| Path | Change |
|------|--------|
| `packages/ui/whatsapp.ts` | Normalize + `buildWhatsAppUrl` (+ missing-phone compose) |
| `packages/ui/WhatsAppShareAction.tsx` | Reusable share UI |
| `packages/ui/whatsapp.test.mjs` | Unit tests |
| `packages/ui/index.ts`, `components.css` | Export + layout |
| `apps/web/lib/shareLinks.ts` | Absolute URLs + safe message templates |
| `apps/web/lib/shareLinks.test.ts` | Message content tests |
| `apps/web/app/staff/page.tsx` | Invite → WhatsApp / Copy link |
| `apps/web/app/team/page.tsx` | Same |
| `apps/web/app/patients/[id]/page.tsx` | Portal enroll share + care WA uses component |
| `apps/web/app/onboarding/page.tsx` | Points to Staff WhatsApp share |

## Tests run

| Suite | Result |
|-------|--------|
| `npm run ui:typecheck` | Pass |
| `npm run ui:test` | **24 passed** (imaging + whatsapp) |
| `npm run web:typecheck` | Pass |
| `vitest` `lib/shareLinks.test.ts` | **2 passed** |
| `pytest tests/unit/test_whatsapp_link.py tests/api/test_followups_comms.py` | **7 passed** |

## Screenshots

Not required for PASS; component is covered by unit tests + typed wiring. Facilitators can capture from Staff → Invitations after create.

## Known limitations

- Portal activation has **no** server-issued one-time URL; share is password-reset + portal instructions.  
- Missing phone opens WhatsApp contact picker (`wa.me/?text=`), not a send.  
- No automated delivery.  
