# P3.0 — Gap Backlog (actionable)

Priority: **P0** pilot-blocking for self-serve / day-1 UI | **P1** material friction | **P2** specialty / polish | **Defer** intentional.

---

## P0-1 Workspace provisioning UI

- **User problem:** After signup, clinic owner sees empty tenant picker; cannot create a workspace in-browser.  
- **Evidence:** No `apps/web` call to `POST /api/v1/workspaces`; documented in `o1.5r-two-pilot-e2e.md`.  
- **Expected:** Authenticated “Create clinic” form (name, slug, timezone, specialty, location) with Idempotency-Key.  
- **API:** Existing `workspaces.py` — no schema change required.  
- **Frontend:** New page or home CTA; DESIGN.md / `packages/ui`.  
- **Security:** Owner from session only; rate-limit; no client-supplied owner ids.  
- **DB:** None.  
- **Tests:** Playwright or Vitest + API regression `test_workspaces_api.py`.  
- **Deps:** None.

## P0-2 Practitioner approval UI

- **User problem:** Provisioned owner practitioner is `pending`; schedule hides them; booking fails.  
- **Evidence:** `workspaces/service.py` pending status; `scheduling/service.py` requires verified; E2E approves via service.  
- **Expected:** Admin action “Approve practitioner” calling `POST .../verification`.  
- **API:** Existing.  
- **Frontend:** `/admin` or `/staff`.  
- **Security:** `settings.manage` / verification permission.  
- **Tests:** UI + `test_tenants_api.py` practitioner verify.  
- **Deps:** P0-1 optional if operator uses API.

## P0-3 Portal enrollment UI

- **User problem:** Cannot link patient user to portal without API.  
- **Evidence:** `POST .../portal-links` in `tenants.py`; no patients UI.  
- **Expected:** Patient chart action “Enable portal access”.  
- **Security:** Staff-only; audit; least privilege.  
- **Tests:** Portal security regressions.  
- **Deps:** None.

## P1-1 Invite accept page

- **User problem:** Invited staff cannot accept in web app.  
- **Evidence:** `invites.py` API; token shown on team/staff pages only.  
- **Expected:** `/invites/accept?token=` flow.  
- **Deps:** Email delivery (or paste token).

## P1-2 Staff schedule availability picker

- **User problem:** Desk books free-form datetime; portal has slots, staff does not.  
- **Evidence:** `GET .../availability` unused on `/schedule`.  
- **Expected:** Slot picker using availability API.

## P1-3 Portal document download

- **User problem:** Documents list with no download.  
- **Evidence:** `download_available=False` in `portal.py`.  
- **Expected:** Server-bound access grant; no client `storage_key`.  
- **Security:** Must fix upload key binding first (Risk § file upload).

## P1-4 Nav / labeling cleanup

- **User problem:** “Plans” vs “Treatment”; Team vs Staff; billing subroutes hidden.  
- **Evidence:** `nav.ts`.  
- **Expected:** Rename SaaS catalog; group billing; mobile nav collapse.

## P1-5 Production notification provider

- **User problem:** Verify/invite email only via DEV console.  
- **Evidence:** `NOTIFY_PROVIDER` limited; `o1.1-delivery-limitation.md`.  
- **Expected:** SES/SMTP adapter; fail-closed in prod.

## P2-1 Ophthalmology specialty pack (post-discovery)

- **User problem:** Eye pilot needs specialty documentation after checklist.  
- **Evidence:** Discovery-only maturity; no module.  
- **Expected:** Spec from checklist → gated feature pack.  
- **Do not implement** without specialist validation.

## P2-2 Operational reports export

- **User problem:** Dashboard only; `reports.view` unused.  
- **Expected:** Bounded CSV exports for appointments/AR.

## Defer

| Item | Reason |
|------|--------|
| P2.6 Razorpay / recurring SaaS | Strategic pause |
| Portal reschedule | Policy TBD; cancel+rebook works |
| X-ray acquisition / annotation | Dentist uses existing equipment |
| Automated WhatsApp send | Click-to-chat only |
| Patient merge | Duplicates warned; merge is clinical decision |

## Recommended implementation sequence

1. P0-1 → P0-2 → P0-3 (unblocks self-serve + portal)  
2. P1-1 → P1-5 (team + email)  
3. P1-2 → P1-3 → P1-4 (desk UX + portal files)  
4. Eye discovery → P2-1 only if validated  
5. Keep SaaS payments frozen through first pilot week
