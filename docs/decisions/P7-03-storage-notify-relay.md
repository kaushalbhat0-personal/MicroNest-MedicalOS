# P7-03 — Storage, notifications, branding, and the on-prem relay

Status: accepted (P7 preview slice).

## Storage

- `StoragePort` is deployment-neutral. Adapters: `local` (dev/test, volume),
  `s3` (preview MinIO, cloud S3, private S3). Selection is configuration
  only — no domain branches.
- Buckets are private, objects keyed server-side, reads via expiring
  presigned references (never raw paths, never public listing — smoke-tested).
- Tenant/object ownership and quarantine semantics stay in the domain layer;
  the adapter enforces key hygiene only.

## Notifications

- `NotifyPort` with `dev-console` (dev/test, `health()=False`) and `none`
  (preview/production: explicitly unavailable, `send()` fails closed).
- Payloads crossing the port carry references only (`assert_port_safe`
  enforced + tested). No PHI in notification payloads by construction.
- Real SES/SMS providers are post-P7. The worker selects the provider from
  `NOTIFY_PROVIDER` and refuses to boot on unknown/misconfigured values.

## Branding / licensing (explicitly out of the P7 slice)

- `branding` and `licensing` modules are stubs. White-label branding
  resolution and offline license verification are NOT implemented.
- Branding must never alter authorization or tenant isolation (constraint
  recorded for the implementing phase; no code exists to violate it yet).

## Future outbound-only portal relay (design, not implemented)

On-prem keeps the database and inbound ports closed. When portal access is
needed, the customer environment initiates outbound connections to the relay:

1. Local agent opens an outbound TLS session (no inbound firewall rule, no
   public DB, no port forwarding).
2. Relay issues authenticated, scoped, expiring envelopes per request
   (patient document fetch, appointment sync); verified locally before use.
3. No permanent clinical data replication by default; patient documents use
   expiring shares; relay failure never mutates local clinical workflows.

P7 ships no sync code — only this contract, so a future implementation has a
fixed target.
