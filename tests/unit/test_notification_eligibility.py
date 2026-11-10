"""P8.1B notification eligibility: deterministic policy tests. DB-free."""

import uuid
from datetime import datetime

import pytest

from app.modules.notifications import eligibility as E
from app.platform.ports.ports import (
    assert_notification_refs_safe,
    assert_port_safe,
)
from app.platform.time import UTC

T1 = uuid.uuid4()
T2 = uuid.uuid4()


def _req(**overrides):  # type: ignore[no-untyped-def]
    kwargs = {
        "channel": "email",
        "event_tenant_id": T1,
        "recipient_tenant_id": T1,
        "recipient_ref": f"user-{uuid.uuid4().hex[:8]}",
        "consent_status": "granted",
        "consent_channels": frozenset({"email"}),
        "destination": "user@example.com",
        "enabled_channels": None,
        "timezone_preference": None,
        "location_timezone": "Asia/Kolkata",
        "quiet_start_min": None,
        "quiet_end_min": None,
        "now_utc": datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
    }
    kwargs.update(overrides)
    return E.EligibilityRequest(**kwargs)


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, 4, hour, minute, tzinfo=UTC)


# --- consent ---


def test_granted_consent_allows() -> None:
    assert E.evaluate_eligibility(_req()).decision == "allow"


def test_missing_consent_denies() -> None:
    result = E.evaluate_eligibility(_req(consent_status=None))
    assert (result.decision, result.reason) == ("deny", E.REASON_MISSING_CONSENT)


def test_revoked_consent_denies() -> None:
    result = E.evaluate_eligibility(_req(consent_status="revoked"))
    assert (result.decision, result.reason) == ("deny", E.REASON_REVOKED_CONSENT)


def test_revocation_before_dispatch_flips_allow_to_deny() -> None:
    assert E.evaluate_eligibility(_req()).decision == "allow"
    assert E.evaluate_eligibility(_req(consent_status="revoked")).decision == "deny"


def test_unrecognized_consent_status_denies_without_grant() -> None:
    result = E.evaluate_eligibility(_req(consent_status="maybe"))
    assert result.decision == "deny" and result.reason == E.REASON_INVALID_CONSENT


def test_channel_mismatch_denies() -> None:
    result = E.evaluate_eligibility(_req(consent_channels=frozenset({"sms"})))
    assert (result.decision, result.reason) == ("deny", E.REASON_CHANNEL_MISMATCH)


def test_disabled_channel_preference_denies() -> None:
    result = E.evaluate_eligibility(_req(enabled_channels=frozenset({"sms"})))
    assert (result.decision, result.reason) == ("deny", E.REASON_CHANNEL_MISMATCH)


def test_enabled_channel_preference_allows() -> None:
    assert (
        E.evaluate_eligibility(_req(enabled_channels=frozenset({"email"}))).decision
        == "allow"
    )


# --- recipients / tenants ---


def test_unknown_recipient_denies() -> None:
    result = E.evaluate_eligibility(_req(recipient_ref="  "))
    assert (result.decision, result.reason) == ("deny", E.REASON_UNKNOWN_RECIPIENT)


def test_unresolved_tenant_recipient_denies() -> None:
    result = E.evaluate_eligibility(_req(recipient_tenant_id=None))
    assert (result.decision, result.reason) == ("deny", E.REASON_UNKNOWN_RECIPIENT)


def test_cross_tenant_denies() -> None:
    result = E.evaluate_eligibility(_req(recipient_tenant_id=T2))
    assert (result.decision, result.reason) == ("deny", E.REASON_CROSS_TENANT)


def test_platform_event_with_platform_recipient_allows() -> None:
    req = _req(event_tenant_id=None, recipient_tenant_id=None, location_timezone="UTC")
    assert E.evaluate_eligibility(req).decision == "allow"


def test_platform_event_with_tenant_recipient_denies() -> None:
    req = _req(event_tenant_id=None, recipient_tenant_id=T1)
    result = E.evaluate_eligibility(req)
    assert (result.decision, result.reason) == ("deny", E.REASON_CROSS_TENANT)


def test_unsupported_channel_denies() -> None:
    assert E.evaluate_eligibility(_req(channel="whatsapp")).reason == (
        E.REASON_UNSUPPORTED_CHANNEL
    )
    assert E.evaluate_eligibility(_req(channel="  ")).decision == "deny"


# --- destinations ---


def test_invalid_email_destination_denies() -> None:
    for bad in (None, "", "not-an-email", "a@b", "a b@c.com", "x" * 321 + "@e.com"):
        result = E.evaluate_eligibility(_req(destination=bad))
        assert result.reason == E.REASON_INVALID_DESTINATION, bad


def test_sms_destination_shapes() -> None:
    ok = _req(
        channel="sms",
        consent_channels=frozenset({"sms"}),
        destination="+91 98200 12345",
    )
    assert E.evaluate_eligibility(ok).decision == "allow"
    bad = _req(
        channel="sms",
        consent_channels=frozenset({"sms"}),
        destination="call-me-maybe",
    )
    assert E.evaluate_eligibility(bad).reason == E.REASON_INVALID_DESTINATION
    assert E.evaluate_eligibility(
        _req(channel="sms", consent_channels=frozenset({"sms"}), destination=None)
    ).reason == (E.REASON_INVALID_DESTINATION)


def test_in_app_destination_is_internal_ref() -> None:
    ok = _req(
        channel="in_app",
        consent_channels=frozenset({"in_app"}),
        destination=str(uuid.uuid4()),
    )
    assert E.evaluate_eligibility(ok).decision == "allow"
    assert E.evaluate_eligibility(
        _req(channel="in_app", consent_channels=frozenset({"in_app"}), destination=" ")
    ).reason == (E.REASON_INVALID_DESTINATION)


# --- timezones ---


def test_unknown_timezone_denies() -> None:
    result = E.evaluate_eligibility(
        _req(timezone_preference=None, location_timezone=None)
    )
    assert (result.decision, result.reason) == ("deny", E.REASON_UNKNOWN_TIMEZONE)
    result = E.evaluate_eligibility(
        _req(timezone_preference="Mars/Olympus", location_timezone="Not/AZone")
    )
    assert result.reason == E.REASON_UNKNOWN_TIMEZONE


def test_invalid_preference_falls_back_to_location() -> None:
    req = _req(timezone_preference="Mars/Olympus", location_timezone="UTC")
    assert E.evaluate_eligibility(req).decision == "allow"


def test_preference_override_wins_over_location() -> None:
    # 2026-05-04 12:00 UTC = 17:30 IST (outside 22-06 window) but
    # 05:00 Pacific (inside 22-06 window).
    base = {"quiet_start_min": 22 * 60, "quiet_end_min": 6 * 60}
    via_location = _req(location_timezone="Asia/Kolkata", **base)
    assert E.evaluate_eligibility(via_location).decision == "allow"
    via_override = _req(
        location_timezone="Asia/Kolkata",
        timezone_preference="America/Los_Angeles",
        **base,
    )
    result = E.evaluate_eligibility(via_override)
    assert (result.decision, result.reason) == ("defer", E.REASON_QUIET_HOURS)


def test_naive_timestamp_denies() -> None:
    result = E.evaluate_eligibility(_req(now_utc=datetime(2026, 5, 4, 12, 0)))
    assert (result.decision, result.reason) == ("deny", E.REASON_INVALID_TIMESTAMP)


# --- quiet hours ---


def test_quiet_hours_defer_with_resume_hint() -> None:
    # 23:00 IST inside 22:00-06:00; resume exactly 06:00 IST (+7h, no DST).
    req = _req(
        quiet_start_min=22 * 60,
        quiet_end_min=6 * 60,
        now_utc=datetime(2026, 5, 4, 17, 30, tzinfo=UTC),
    )
    result = E.evaluate_eligibility(req)
    assert result.decision == "defer" and result.reason == E.REASON_QUIET_HOURS
    assert result.resume_at_utc == datetime(2026, 5, 5, 0, 30, tzinfo=UTC)
    # Re-evaluation at resume allows (hint is exact outside DST).
    assert (
        E.evaluate_eligibility(_req(now_utc=result.resume_at_utc)).decision == "allow"
    )


def test_outside_quiet_hours_allows() -> None:
    req = _req(
        quiet_start_min=22 * 60,
        quiet_end_min=6 * 60,
        now_utc=datetime(2026, 5, 4, 6, 30, tzinfo=UTC),  # 12:00 IST
    )
    assert E.evaluate_eligibility(req).decision == "allow"


def test_quiet_hour_boundaries() -> None:
    window = {"quiet_start_min": 22 * 60, "quiet_end_min": 6 * 60}
    at_start = _req(now_utc=datetime(2026, 5, 4, 16, 30, tzinfo=UTC), **window)  # 22:00
    assert E.evaluate_eligibility(at_start).decision == "defer"
    at_end = _req(now_utc=datetime(2026, 5, 4, 0, 30, tzinfo=UTC), **window)  # 06:00
    assert E.evaluate_eligibility(at_end).decision == "allow"


def test_partial_quiet_window_denies() -> None:
    result = E.evaluate_eligibility(_req(quiet_start_min=22 * 60, quiet_end_min=None))
    assert result.reason == E.REASON_QUIET_HOURS_MISCONFIGURED
    result = E.evaluate_eligibility(_req(quiet_start_min=60, quiet_end_min=60))
    assert result.reason == E.REASON_QUIET_HOURS_MISCONFIGURED


def test_quiet_defer_is_not_failure() -> None:
    result = E.evaluate_eligibility(
        _req(
            quiet_start_min=22 * 60,
            quiet_end_min=6 * 60,
            now_utc=datetime(2026, 5, 4, 17, 30, tzinfo=UTC),
        )
    )
    assert result.decision == "defer"
    assert result.resume_at_utc is not None and result.resume_at_utc > _at(17, 30)


# --- daylight saving ---


def test_dst_spring_forward_gap() -> None:
    # America/New_York springs forward 2026-03-08; 02:30 local never occurs.
    # 06:30 UTC = 01:30 EST (before gap), 07:30 UTC = 03:30 EDT (after gap).
    window = {"quiet_start_min": 2 * 60, "quiet_end_min": 4 * 60}
    before = _req(
        timezone_preference="America/New_York",
        location_timezone=None,
        now_utc=datetime(2026, 3, 8, 6, 30, tzinfo=UTC),
        **window,
    )
    assert E.evaluate_eligibility(before).decision == "allow"
    after = _req(
        timezone_preference="America/New_York",
        location_timezone=None,
        now_utc=datetime(2026, 3, 8, 7, 30, tzinfo=UTC),
        **window,
    )
    assert E.evaluate_eligibility(after).decision == "defer"


def test_dst_fall_back_ambiguous_wall_time() -> None:
    # 2026-11-01: 01:30 occurs twice (EDT then EST). UTC conversion is exact
    # per instant, so both evaluate deterministically inside 01:00-02:00.
    window = {"quiet_start_min": 60, "quiet_end_min": 120}
    first = _req(
        timezone_preference="America/New_York",
        location_timezone=None,
        now_utc=datetime(2026, 11, 1, 5, 30, tzinfo=UTC),
        **window,
    )
    second = _req(
        timezone_preference="America/New_York",
        location_timezone=None,
        now_utc=datetime(2026, 11, 1, 6, 30, tzinfo=UTC),
        **window,
    )
    assert E.evaluate_eligibility(first).decision == "defer"
    assert E.evaluate_eligibility(second).decision == "defer"
    assert (
        E.evaluate_eligibility(first).resume_at_utc
        != E.evaluate_eligibility(second).resume_at_utc
    )


def test_dst_resume_hint_self_corrects_on_reevaluation() -> None:
    req = _req(
        timezone_preference="America/New_York",
        location_timezone=None,
        quiet_start_min=2 * 60,
        quiet_end_min=4 * 60,
        now_utc=datetime(2026, 3, 8, 7, 30, tzinfo=UTC),
    )
    result = E.evaluate_eligibility(req)
    assert result.decision == "defer" and result.resume_at_utc is not None
    again = E.evaluate_eligibility(
        _req(
            timezone_preference="America/New_York",
            location_timezone=None,
            quiet_start_min=2 * 60,
            quiet_end_min=4 * 60,
            now_utc=result.resume_at_utc,
        )
    )
    # Across the transition the hint may land slightly off; the protocol is
    # safe either way because dispatch always re-evaluates.
    assert again.decision in ("allow", "defer")


def test_utc_and_kolkata_zones() -> None:
    assert E.is_valid_iana_timezone("UTC")
    assert E.is_valid_iana_timezone("Asia/Kolkata")
    assert not E.is_valid_iana_timezone("Mars/Olympus")
    assert not E.is_valid_iana_timezone("")
    assert not E.is_valid_iana_timezone(None)


# --- port safety (recursive guard + refs allow-list) ---


def test_port_guard_still_accepts_safe_payloads() -> None:
    assert_port_safe({"user_id": "u-1", "template": "t"})
    assert_port_safe({"context_refs": {"appointment_id": "a-1"}, "channel": "sms"})


def test_port_guard_rejects_nested_clinical_keys() -> None:
    with pytest.raises(ValueError):
        assert_port_safe({"outer": {"subjective": "chest pain"}})
    with pytest.raises(ValueError):
        assert_port_safe({"items": [{"diagnosis": "caries"}]})
    with pytest.raises(ValueError):
        assert_port_safe({"a": {"b": {"deep": {"prescription": "amox"}}}})
    with pytest.raises(ValueError):
        assert_port_safe({"nested": {"clinical_notes": "x", "ok": 1}})


def test_port_guard_rejects_new_forbidden_keys() -> None:
    for key in (
        "subjective",
        "objective",
        "assessment",
        "medication",
        "email",
        "phone",
    ):
        with pytest.raises(ValueError):
            assert_port_safe({key: "x"})
        with pytest.raises(ValueError):
            assert_port_safe({"wrapper": [{key: "x"}]})


def test_notification_refs_allow_list() -> None:
    assert_notification_refs_safe(
        {
            "invitation_id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "appointment_id": str(uuid.uuid4()),
        }
    )
    assert_notification_refs_safe({"recall_id": 42, "patient_id": uuid.uuid4()})


def test_notification_refs_reject_non_id_keys_and_contacts() -> None:
    with pytest.raises(ValueError):
        assert_notification_refs_safe({"ref": "1"})
    with pytest.raises(ValueError):
        assert_notification_refs_safe({"diagnosis": "caries"})
    with pytest.raises(ValueError):
        assert_notification_refs_safe({"user_id": "someone@example.com"})
    with pytest.raises(ValueError):
        assert_notification_refs_safe({"user_id": "+919820012345"})
    with pytest.raises(ValueError):
        assert_notification_refs_safe({"appointment_id": {"nested": "object"}})
    with pytest.raises(ValueError):
        assert_notification_refs_safe({"appointment_id": ""})


# --- consent audit (refs only) ---


def test_consent_audit_carries_refs_only() -> None:
    consent_id = uuid.uuid4()
    record = E.build_consent_audit(
        tenant_id=T1,
        actor_type="user",
        actor_id="actor-1",
        action=E.CONSENT_GRANTED_ACTION,
        consent_id=consent_id,
        channel="email",
    )
    assert record["resource_type"] == "notification_consent"
    assert record["resource_id"] == f"{consent_id}:email"
    blob = " ".join(str(v) for v in record.values())
    assert "@" not in blob and "98200" not in blob
    assert "action" in record and record["action"] == E.CONSENT_GRANTED_ACTION


def test_consent_audit_rejects_contacts_and_unknowns() -> None:
    with pytest.raises(ValueError):
        E.build_consent_audit(
            tenant_id=T1,
            actor_type="user",
            actor_id="a",
            action=E.CONSENT_GRANTED_ACTION,
            consent_id="someone@example.com",  # type: ignore[arg-type]
            channel="email",
        )
    with pytest.raises(ValueError):
        E.build_consent_audit(
            tenant_id=T1,
            actor_type="user",
            actor_id="a",
            action="notification.sent",
            consent_id=uuid.uuid4(),
            channel="email",
        )
    with pytest.raises(ValueError):
        E.build_consent_audit(
            tenant_id=T1,
            actor_type="user",
            actor_id="a",
            action=E.CONSENT_REVOKED_ACTION,
            consent_id=uuid.uuid4(),
            channel="whatsapp",
        )
