# Communications Architecture (Future Design — No Implementation)

Status: **FUTURE DESIGN ONLY** (architecture alignment, 2026-11-08). No provider code,
no credentials, no migration, no endpoint in this slice.
Companions: `frictionless-onboarding.md`, `specialty-pack-architecture.md`.
Sources inspected: `platform/ports/ports.py`, `platform/adapters/notify.py`,
`modules/notifications/{service,eligibility}.py`, `platform/config.py`,
`api/v1/{signup,account,tenants}.py`, `docs/commercial/*.md` (discovery).

## 1. APPROVED direction (binding constraints)

1. **Platform provides email as a platform offering.** Clinic BYO email is optional.
2. **Provider-neutral adapter architecture.** Business logic depends on ports;
   only adapter selection branches on deployment/provider.
3. **WhatsApp Web = manual handoff. WhatsApp API (WATI / other approved BSPs) =
   automated provider delivery.** Never treat them as equivalent in UX, copy, audit,
   or delivery semantics.
4. **Clinic communication configuration is optional during signup** and skippable.
   A clinic configures it later. Account verification (platform identity) MUST NOT
   depend on any clinic communication setting.
5. **Do not implement any provider in this task.** This doc is design only.

## 2. What exists today (verified — do not regress)

- `NotifyPort` / `NotifyRequest{channel,to_ref,template,locale,context_refs,tenant_id}` /
  `NotifyResult` (`ports.py:33-64`). `channel` today includes `whatsapp` as a *string
  constant only*; the eligibility policy (below) deliberately denies it.
- `build_notify_adapter` (`adapters/notify.py`): `dev-console` (dev/test logging,
  `health()==False`) and `none` (fail-closed raise, `health()==False`). No SES/SMTP/SMS
  provider exists. `NOTIFY_PROVIDER` allow-list is `{"dev-console","none"}` (`config.py:31`).
  Preview/prod boot refuses `dev-console`.
- Eligibility gate P8.1B (`modules/notifications/eligibility.py`): pure, transport-
  independent, evaluated before dispatch. `SUPPORTED_CHANNELS = {email, sms, in_app}` —
  `whatsapp` is **unsupported → deny** (never silently mapped). Consent-required
  (missing/revoked/channel-mismatch deny), destination-shaped (email regex, E.164-ish
  phone), tenant-scoped (cross-tenant deny), quiet-hours defer, IANA timezone resolution
  (`is_valid_iana_timezone`, reused pattern for provisioning validation).
- Port safety: `FORBIDDEN_PORT_KEYS` blacklist + `assert_notification_refs_safe`
  (`*_id`-shaped `context_refs` only; no `token/email/phone` content). Producers
  (`signup.py`, `account.py`, `tenants.py`) enqueue refs-only (`user_id`, `invitation_id`,
  `appointment_id`, `verification_id`).
- Templates referenced but not delivered in prod: `verify_email`, `password_reset`,
  `staff_invite` (tenant-scoped), plus scheduling/recall reminders (eligibility-covered).
- Outbox (`outbox_events`, `notification.requested`) is the durability seam; the worker
  dispatches through the selected adapter with retries then `dead`.

## 3. Target architecture (PROPOSED — recommended)

```
domain code  ->  request_notification(outbox, refs-only)
  -> eligibility.evaluate (consent, destination, tenant, quiet, tz)
  -> dispatcher resolves destination server-side (NEVER trusts to_ref/client input)
  -> adapter selection:
       platform email pool  OR  clinic BYO email provider  (per-tenant override)
       WATI / approved BSP  (WhatsApp API, only when clinic connected)
       WhatsApp Web handoff (manual: deep-link + copy, NO delivery claim)
  -> send -> delivery receipt -> audit (refs only) + metering event
```

### 3.1 Platform email provider (PROPOSED)

- One platform-operated transactional email sender (e.g., SES-equivalent; selection O4).
  Credentials live in platform secret management, never in tenant rows, never in the browser.
- Used for: platform-identity mail (`verify_email`, `password_reset`) with
  `tenant_id=None`; default clinic mail until the clinic connects BYO.
- Health semantics: `health()==True` only when a real provider is configured and reachable.
  `dev-console`/`none` keep `False` so release gates cannot mistake them for delivery.
- Identity mail MUST work with zero clinic configuration (decouples verification from
  clinic comms — approved).

### 3.2 Clinic BYO email provider (PROPOSED)

- Optional per-tenant override: Resend / API / SMTP (product to finalize the list;
  Resend named in approved direction as one option).
- Storage: provider type + credentials **encrypted at rest** (envelope encryption, KMS/
  secret-manager-backed; exact mechanism per deployment profile), tenant-isolated rows
  (RLS `tenant_id = SETTING`, same pattern as `subscriptions`), never returned to clients.
- Selection precedence per message: clinic BYO (if configured + healthy + consent covers)
  else platform pool. Identity mail (`tenant_id=None`) always uses the platform pool.
- Validation on save: credential-shape check + test-send to a staff-controlled address
  (rate-limited) before activation; failures never leak secrets in errors/logs.
- Rotation/revocation: staff action (`STAFF_MANAGE`-gated future endpoint), audit refs-only,
  in-flight outbox items keep the adapter resolved at dispatch time (no mid-flight swap).

### 3.3 WhatsApp Web manual handoff (PROPOSED)

- NOT automated delivery. UX: per-recipient "Send via WhatsApp" action that opens a
  `wa.me` deep link with prefilled, consent-checked text + logs a `whatsapp.handoff`
  audit event (refs only: message id, actor, recipient ref — never content).
- Delivery status: `handoff` (terminal, informational). No `delivered/read/failed` claims.
  Copy MUST say "opens WhatsApp — you send it" to avoid equivalence confusion.
- No credentials, no webhook, no phone-number hosting. Works on all deployments
  including on-prem without a BSP contract.

### 3.4 WATI adapter (PROPOSED)

- Automated delivery only when the clinic has connected its own WATI account
  (API key/endpoint stored encrypted per §3.2 pattern, tenant-isolated).
- Adapter implements `NotifyPort` with `channel="whatsapp"` (requires lifting the current
  eligibility deny for whatsapp → allow only when a whatsapp adapter is configured AND
  consent + destination pass; default stays deny).
- Template-message discipline: WATI/BSP templates approved out-of-band; the adapter maps
  internal `template` keys to provider template ids; session vs template windows enforced
  by the adapter, surfaced as `deferred/failed` with provider refs.
- Delivery statuses: `queued → sent → delivered → read / failed` (provider receipts;
  exact vocabulary per BSP). Receipts update message state + audit refs; content never
  stored in receipts.

### 3.5 Future WhatsApp Business API adapters (PROPOSED)

- Same seam as WATI: one adapter per approved BSP (list approved by product/security;
  no arbitrary webhook URLs from the browser). Each adapter is a small, reviewed class
  behind `NotifyPort`; selection is per-tenant config (`provider = wati | bsp-x | web-handoff`).
- No generic "paste any BSP endpoint" feature. New BSP = code + security review +
  eligibility/template mapping + tests.

### 3.6 Encrypted provider credentials (PROPOSED)

- Table sketch (FUTURE, not built): `tenant_comm_providers{id, tenant_id FK CASCADE,
  kind (email-resend/email-smtp/whatsapp-wati/whatsapp-bsp), provider_ref, enc_config
  (binary, envelope-encrypted), status, created_by, created_at/updated_at}`.
  RLS tenant-isolated; `hos_app` least-privilege; decryption only in the dispatch worker,
  never in API reads. Key rotation via platform key-management runbook (per deployment).
- Invariants: secrets never in logs, outbox payloads, audit details, API responses, or
  error messages. Test-send uses masked identifiers (`…1234`).

### 3.7 Tenant isolation (PROPOSED)

- Every comm row carries `tenant_id`; RLS `tenant_id = SETTING` (same expression as
  `0005_rls.py:24`). Platform-identity mail (`tenant_id NULL`) resolves platform
  identities only, never patient rows (eligibility §198-206 already enforces).
- Cross-tenant `to_ref` is unresolvable by construction (service getters raise
  `NotFoundError` on mismatch). Dispatcher re-reads consent at dispatch time.

### 3.8 Delivery status semantics (PROPOSED)

| State | Meaning | Applies to |
|---|---|---|
| `queued` | outbox accepted, eligibility passed | all |
| `handoff` | WhatsApp Web link generated; manual send by user | web handoff (terminal) |
| `sent` | provider accepted | email/API/BSP |
| `delivered` / `read` | provider receipt | where the provider offers it |
| `deferred` | quiet-hours or provider 429/5xx; worker reschedules without consuming a retry as failure | all automated |
| `failed` / `dead` | terminal after retries; surfaced to staff with refs + next action | all automated |

Message content is never stored alongside status; status rows carry refs
(`tenant_id`, `message_id`, `provider_ref`, `template`, `reason_code`).

### 3.9 Consent and communication preferences (PROPOSED)

- Extend the existing consent model (eligibility `consent_status` + `consent_channels` +
  `enabled_channels` + quiet windows) to WhatsApp when the adapter lands. Missing consent
  denies; revocation takes effect at next dispatch evaluation.
- Channel coverage: `email`, `sms`, `whatsapp`, `in_app` (whatsapp stays denied until
  §3.4 lands). Per-recipient `enabled_channels` explicit set gates sends.
- Clinic-level sender identity (from-name, reply-to, WATI number) is configuration, not
  consent; recipient consent is per-recipient and mandatory.

### 3.10 Usage metering boundary (PROPOSED)

- Metering events (`tenant_id`, `channel`, `template`, `count`, `provider_ref`) emitted
  on dispatch outcome for future quota/entitlement checks (O2). Metering NEVER blocks
  sends in O1; enforcement points are O2+ and read the subscription row server-side.
- Identity mail (`verify_email`, `password_reset`) is platform-cost, not clinic-metered.

### 3.11 Provider failure behavior (PROPOSED)

- Fail closed, never silently drop: adapter exceptions → outbox retry with backoff
  (existing worker), then `dead` with staff-visible refs + operator alert.
- `none` provider stays raise-always (current behavior preserved as the honest
  no-provider state). `dev-console` stays dev/test-only (boot gate preserved).
- Per-tenant provider outage (bad BYO key, WATI 401) degrades to platform pool for
  eligible clinic mail where policy allows, else `deferred` + staff notice — never to
  an unconsented channel, never to a different tenant's provider.

## 4. Deferred (explicitly NOT in this task)

Provider selection (SES vs alternatives), credential schema, dispatcher code, template
management UI, consent-center UI, metering tables, DLT/consent-registry integration,
opt-out keyword handling, cost/quota policy. All O2/O4.

## 5. Unresolved (needs owner sign-off)

1. BYO provider list (Resend mandatory? SMTP allowed?).
2. WATI vs additional BSP priority order.
3. Test-send policy + rate limits.
4. Sender-identity verification (SPF/DKIM/WhatsApp number approval) ownership.
5. Retention of delivery receipts + message metadata (D4-adjacent).
