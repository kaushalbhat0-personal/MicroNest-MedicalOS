"""Notification eligibility policy (P8.1B).

A deterministic, transport-independent gate evaluated BEFORE any provider
dispatch. Pure by design: no database access, no network, no clock reads —
the caller supplies a server-resolved snapshot and the current time.

Recipient-resolution contract (enforced by the future dispatcher, not here):
- `to_ref` on the wire is OPAQUE and today heterogeneous (raw invite email,
  user UUID, raw phone — see api/v1/tenants.py, account.py, scheduling.py).
  It must NEVER be trusted as a destination.
- The dispatcher resolves the recipient server-side immediately before
  dispatch and builds an EligibilityRequest:
  - tenant-scoped recipients (patient/user/invitation rows) are read with
    the event's tenant pinned; cross-tenant rows are unresolvable by
    construction (service getters raise NotFoundError on tenant mismatch).
  - destinations (email/phone) come ONLY from server-read rows or the
    invitation row created by authorized staff — never from client input.
  - platform-scoped events (event_tenant_id None, e.g. password_reset)
    resolve platform identities (users) only, never patient rows.
- Consent status is re-read at dispatch time; a revocation landing between
  enqueue and dispatch flips the next evaluation to deny.

Decisions: "allow" | "deny" | "defer".
- deny: terminal for this evaluation (missing/revoked consent, bad
  destination, unknown/cross-tenant recipient, unknown timezone).
- defer: quiet-hours only — NOT a provider failure; the worker must
  reschedule without consuming a retry attempt.

This module defines no legal consent rules and no quiet-hour defaults:
missing consent denies, and quiet windows are explicit inputs. Product and
clinic/legal owners must approve defaults before any migration or wiring.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.platform.time import UTC

# Channels the P8.1 policy can evaluate. WhatsApp automation is out of scope
# (product decision): it is denied as unsupported, never silently mapped.
SUPPORTED_CHANNELS = frozenset({"email", "sms", "in_app"})

CONSENT_GRANTED = "granted"
CONSENT_REVOKED = "revoked"

DECISION_ALLOW = "allow"
DECISION_DENY = "deny"
DECISION_DEFER = "defer"

REASON_OK = "ok"
REASON_UNSUPPORTED_CHANNEL = "unsupported_channel"
REASON_UNKNOWN_RECIPIENT = "unknown_recipient"
REASON_CROSS_TENANT = "cross_tenant"
REASON_MISSING_CONSENT = "missing_consent"
REASON_REVOKED_CONSENT = "revoked_consent"
REASON_INVALID_CONSENT = "invalid_consent_status"
REASON_CHANNEL_MISMATCH = "channel_mismatch"
REASON_INVALID_DESTINATION = "invalid_destination"
REASON_UNKNOWN_TIMEZONE = "unknown_timezone"
REASON_INVALID_TIMESTAMP = "invalid_timestamp"
REASON_QUIET_HOURS = "quiet_hours"
REASON_QUIET_HOURS_MISCONFIGURED = "quiet_hours_misconfigured"

# Conservative destination shapes. Fail closed: anything not matching is
# denied, and the SMTP/SMS adapters re-validate before use.
_MAX_DESTINATION_LEN = 320
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,}$")
_PHONE_CLEAN_RE = re.compile(r"[\s\-().]")
_PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")

# Audit actions for consent changes. Refs only — never contacts or content.
CONSENT_GRANTED_ACTION = "notification.consent.granted"
CONSENT_REVOKED_ACTION = "notification.consent.revoked"
CONSENT_ACTIONS = frozenset({CONSENT_GRANTED_ACTION, CONSENT_REVOKED_ACTION})
CONSENT_RESOURCE_TYPE = "notification_consent"


@dataclass(frozen=True)
class EligibilityRequest:
    """Server-resolved snapshot. Every field is resolved server-side at
    dispatch time; nothing here originates from untrusted client input."""

    channel: str
    event_tenant_id: uuid.UUID | None
    recipient_tenant_id: uuid.UUID | None
    recipient_ref: str
    consent_status: str | None
    consent_channels: frozenset[str] = frozenset()
    destination: str | None = None
    # None = no preferences recorded (neutral; consent still governs).
    # A recorded set not containing the channel denies.
    enabled_channels: frozenset[str] | None = None
    timezone_preference: str | None = None
    location_timezone: str | None = None
    # Minutes since local midnight, [start, end). Both set or both None.
    quiet_start_min: int | None = None
    quiet_end_min: int | None = None
    now_utc: datetime | None = None


@dataclass(frozen=True)
class EligibilityResult:
    decision: str
    reason: str
    # Set only for defer: earliest instant the worker may re-evaluate.
    # A not-before hint — the worker MUST re-evaluate eligibility then.
    resume_at_utc: datetime | None = None


def normalize_channel(channel: str) -> str:
    return (channel or "").strip().lower()


def is_valid_email_destination(value: str | None) -> bool:
    if not value or len(value) > _MAX_DESTINATION_LEN:
        return False
    return _EMAIL_RE.match(value.strip()) is not None


def is_valid_phone_destination(value: str | None) -> bool:
    if not value or len(value) > 32:
        return False
    cleaned = _PHONE_CLEAN_RE.sub("", value.strip())
    return _PHONE_RE.match(cleaned) is not None


def is_valid_in_app_destination(value: str | None) -> bool:
    if not value:
        return False
    text = value.strip()
    return 0 < len(text) <= _MAX_DESTINATION_LEN


def validate_destination(channel: str, destination: str | None) -> bool:
    if channel == "email":
        return is_valid_email_destination(destination)
    if channel == "sms":
        return is_valid_phone_destination(destination)
    if channel == "in_app":
        return is_valid_in_app_destination(destination)
    return False


def is_valid_iana_timezone(name: str | None) -> bool:
    if not name or not str(name).strip():
        return False
    try:
        ZoneInfo(str(name).strip())
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def resolve_recipient_timezone(preference: str | None, location: str | None) -> ZoneInfo | None:
    """Precedence: valid recipient preference override, else valid assigned
    clinic/location timezone. None when neither resolves — the caller must
    deny (unknown_timezone), never guess."""
    for candidate in (preference, location):
        if candidate and str(candidate).strip():
            try:
                return ZoneInfo(str(candidate).strip())
            except (ZoneInfoNotFoundError, ValueError):
                continue
    return None


def _validate_quiet_window(start: int | None, end: int | None) -> bool:
    if start is None and end is None:
        return True
    if start is None or end is None:
        return False
    if not isinstance(start, int) or not isinstance(end, int):
        return False
    if not (0 <= start < 1440 and 0 <= end < 1440):
        return False
    return start != end


def _minutes_in_window(now_min: int, start: int, end: int) -> bool:
    if start < end:
        return start <= now_min < end
    return now_min >= start or now_min < end


def evaluate_eligibility(req: EligibilityRequest) -> EligibilityResult:
    channel = normalize_channel(req.channel)
    if channel not in SUPPORTED_CHANNELS:
        return EligibilityResult(DECISION_DENY, REASON_UNSUPPORTED_CHANNEL)

    if not req.recipient_ref or not req.recipient_ref.strip():
        return EligibilityResult(DECISION_DENY, REASON_UNKNOWN_RECIPIENT)

    # Tenant scope: tenant-scoped events require a same-tenant recipient;
    # platform events (tenant None) accept platform identities only.
    if req.event_tenant_id is not None:
        if req.recipient_tenant_id is None:
            return EligibilityResult(DECISION_DENY, REASON_UNKNOWN_RECIPIENT)
        if req.recipient_tenant_id != req.event_tenant_id:
            return EligibilityResult(DECISION_DENY, REASON_CROSS_TENANT)
    elif req.recipient_tenant_id is not None:
        return EligibilityResult(DECISION_DENY, REASON_CROSS_TENANT)

    # Consent: missing never means granted; only an explicit grant passes.
    status = (req.consent_status or "").strip().lower()
    if not status:
        return EligibilityResult(DECISION_DENY, REASON_MISSING_CONSENT)
    if status == CONSENT_REVOKED:
        return EligibilityResult(DECISION_DENY, REASON_REVOKED_CONSENT)
    if status != CONSENT_GRANTED:
        return EligibilityResult(DECISION_DENY, REASON_INVALID_CONSENT)
    if channel not in {c.strip().lower() for c in req.consent_channels}:
        return EligibilityResult(DECISION_DENY, REASON_CHANNEL_MISMATCH)

    # Preferences: an explicit recorded set not covering the channel denies.
    if req.enabled_channels is not None:
        if channel not in {c.strip().lower() for c in req.enabled_channels}:
            return EligibilityResult(DECISION_DENY, REASON_CHANNEL_MISMATCH)

    if not validate_destination(channel, req.destination):
        return EligibilityResult(DECISION_DENY, REASON_INVALID_DESTINATION)

    if req.now_utc is None or not isinstance(req.now_utc, datetime):
        return EligibilityResult(DECISION_DENY, REASON_INVALID_TIMESTAMP)
    if req.now_utc.tzinfo is None:
        return EligibilityResult(DECISION_DENY, REASON_INVALID_TIMESTAMP)
    now_utc = req.now_utc.astimezone(UTC)

    tz = resolve_recipient_timezone(req.timezone_preference, req.location_timezone)
    if tz is None:
        return EligibilityResult(DECISION_DENY, REASON_UNKNOWN_TIMEZONE)

    if req.quiet_start_min is None and req.quiet_end_min is None:
        return EligibilityResult(DECISION_ALLOW, REASON_OK)
    if not _validate_quiet_window(req.quiet_start_min, req.quiet_end_min):
        return EligibilityResult(DECISION_DENY, REASON_QUIET_HOURS_MISCONFIGURED)

    start = req.quiet_start_min
    end = req.quiet_end_min
    assert start is not None and end is not None
    now_local = now_utc.astimezone(tz)
    now_min = now_local.hour * 60 + now_local.minute
    if _minutes_in_window(now_min, start, end):
        # Not-before hint: wall-clock minutes until the window ends. Across a
        # DST transition the exact end instant may shift by up to an hour;
        # that is safe because the worker MUST re-evaluate on resume.
        delta_min = (end - now_min) % 1440 or 1440
        return EligibilityResult(
            DECISION_DEFER,
            REASON_QUIET_HOURS,
            resume_at_utc=now_utc + timedelta(minutes=delta_min),
        )
    return EligibilityResult(DECISION_ALLOW, REASON_OK)


def build_consent_audit(
    *,
    tenant_id: uuid.UUID,
    actor_type: str,
    actor_id: str,
    action: str,
    consent_id: uuid.UUID,
    channel: str,
) -> dict[str, object]:
    """Refs-only audit kwargs for a consent change, for audit.append().

    consent_id must be the consent row id (UUID) — never an email, phone, or
    message content. Raises ValueError on anything else (fail closed).
    """
    if action not in CONSENT_ACTIONS:
        raise ValueError(f"unknown consent audit action: {action}")
    if normalize_channel(channel) not in SUPPORTED_CHANNELS:
        raise ValueError(f"unsupported channel for consent audit: {channel}")
    if not isinstance(consent_id, uuid.UUID):
        raise ValueError("consent audit requires a consent row UUID, never a contact")
    if not actor_type.strip() or not actor_id.strip():
        raise ValueError("consent audit requires actor references")
    return {
        "tenant_id": tenant_id,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "action": action,
        "resource_type": CONSENT_RESOURCE_TYPE,
        "resource_id": f"{consent_id}:{normalize_channel(channel)}",
        "result": "ok",
    }
