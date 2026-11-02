"""Log scrubbing: sensitive keys and token shapes never survive."""
import logging

from app.platform.logging_setup import SENSITIVE_KEYS, get_logger, scrub


def test_expected_keys_covered() -> None:
    for key in (
        "password", "token", "refresh_token", "otp", "secret",
        "clinical_note", "diagnosis", "prescription",
    ):
        assert key in SENSITIVE_KEYS


def test_scrub_redacts_nested_dicts() -> None:
    payload = {
        "user": "a@b.c",
        "password": "hunter2",
        "nested": {"diagnosis": "caries", "ok": 1},
        "items": [{"token": "abc", "v": 2}],
    }
    out = scrub(payload)
    assert out["password"] == "[REDACTED]"
    assert out["nested"]["diagnosis"] == "[REDACTED]"
    assert out["nested"]["ok"] == 1
    assert out["items"][0]["token"] == "[REDACTED]"
    assert out["items"][0]["v"] == 2
    assert out["user"] == "a@b.c"


def test_scrub_redacts_jwt_shapes_in_free_text() -> None:
    token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    assert "eyJ" not in scrub(f"login with {token} failed")
    assert "[REDACTED-TOKEN]" in scrub(f"login with {token} failed")


def test_logger_filter_installed() -> None:
    logger = get_logger("p1-test-logger")
    assert any(type(f).__name__ == "ScrubbingFilter" for f in logger.filters)
    assert isinstance(logger, logging.Logger)
