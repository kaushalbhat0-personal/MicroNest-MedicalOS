# Ports & Deployment Adapters (P1)

| Port | Interface | P1 adapter | Later |
|---|---|---|---|
| StoragePort | put/get/exists/delete/signed_access | LocalStorageAdapter (./var, HMAC-signed, expiring) | S3/MinIO same interface |
| NotifyPort | send(refs-only request) | DevNotifyAdapter (console, fail-closed, `health()=false`) | SES/SMS/WhatsApp providers |
| ClockPort | now() | system UTC | frozen clock in tests |
| RateLimitPort | allow(scope,key,limit,window) | in-memory buckets | Redis adapter |

Rules: no public buckets, no predictable URLs, no PHI across ports
(`assert_port_safe` + tests), dev adapters refuse prod (`ENV=prod` boot guard +
constructor guard), production readiness requires `health() == true`.
`infrastructure/{cloud,private,on-premise}/` selects adapters; business logic
never branches on deployment.
