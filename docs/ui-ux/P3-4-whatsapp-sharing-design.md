# P3.4 — WhatsApp sharing design

**HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**Approach:** Reusable **user-initiated** `wa.me` compose — never automated send.

## Audit summary (Phase 1)

| Area | Existing | Reuse |
|------|----------|-------|
| Click-to-chat | `backend/.../whatsapp.py` + `POST .../whatsapp-link` (consent-gated, patient) | Yes — care outreach still uses API |
| Phone normalize | `normalize_whatsapp_number` (7–15 digits) | Mirrored in `@healthcare-os/ui/whatsapp` |
| Staff invites | `POST .../invites` returns one-time `token`; accept `/invite?token=` | Frontend share only; token from server |
| Invite revoke/expire | Staff invitations list + revoke | Unchanged |
| Portal enroll | `POST .../portal-links` — no activation token returned | Share `/password-reset` + `/portal` instructions |
| UI system | `Field`, `Input`, `Textarea`, `Checkbox`, `Button`, `Alert` | `WhatsAppShareAction` composed from these |

## Component: `WhatsAppShareAction`

**Package:** `@healthcare-os/ui`

| Control | Behavior |
|---------|----------|
| Recipient phone | Optional; invalid → block open until fixed or cleared |
| Message | Prefill editable, max 500; parent embeds server link |
| Open in WhatsApp | Builds `https://wa.me/<digits>?text=` or `https://wa.me/?text=` if no phone |
| Copy link | Copies `linkToCopy` only (absolute URL from parent) |
| Confirm | Explicit “not sent automatically” + checkbox |
| `resolveOpenUrl` | Optional async (patient consent path calls backend) |

## Supported flows

1. **Staff / practitioner invitation** — Staff & Team pages after `POST /invites`. Role includes `doctor` for practitioner onboarding handoff.  
2. **Patient portal enrollment** — After portal-link create; message uses password-reset + portal URLs (no secret token).  
3. **Care follow-up WhatsApp** — Patient Care tab; still consent-gated via `whatsapp-link` API with editable message.  
4. **Onboarding copy** — Setup step points owners to Staff for WhatsApp share.

## Explicit non-goals

- WhatsApp Business API, webhooks, bulk send, DOM automation  
- Frontend token generation  
- Claiming message delivery  
- PHI / clinical notes in templates  
