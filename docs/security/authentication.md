# Authentication (P1, locked)

- Argon2id passwords (12+ chars), no hashes leave the server.
- HttpOnly + Secure (prod) + SameSite=Lax cookies; Bearer fallback for natives.
- Access 10 min; refresh opaque 48-byte, stored as SHA-256, 30-day rotation,
  reuse detection revokes the family and is audited.
- Logout revokes server-side; password reset revokes all sessions.
- Invitations: single-use 256-bit token, 7-day expiry; claim binds user+membership.
- Rate limits: login 10/min/IP + 5/min/account (in-memory P1, Redis port later).
- Auth failures return 401 without raising so security-audit writes commit.
- No MFA yet (P5); recovery codes with admin-assisted reset (P5).
