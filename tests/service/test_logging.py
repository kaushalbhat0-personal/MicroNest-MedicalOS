"""Logging: sensitive material never reaches logs — end to end."""

import logging


def test_failed_login_does_not_log_password(
    client, owner_db, make_owner_user, caplog
) -> None:  # type: ignore[no-untyped-def]
    make_owner_user(email="log1@example.com")
    with caplog.at_level(logging.INFO):
        r = client.post(
            "/api/v1/auth/login",
            json={"email": "log1@example.com", "password": "secret-pw- hunter2"},
        )
    assert r.status_code == 401
    assert "secret-pw" not in caplog.text and "hunter2" not in caplog.text


def test_scrubbing_filter_applies_to_app_loggers(caplog) -> None:  # type: ignore[no-untyped-def]
    from app.platform.logging_setup import get_logger

    logger = get_logger("p1-hygiene-probe")
    with caplog.at_level(logging.INFO):
        logger.info({"password": "pw123", "diagnosis": "caries", "ok": True})
    assert "pw123" not in caplog.text
    assert "caries" not in caplog.text
    assert "[REDACTED]" in caplog.text


def test_outbox_never_carries_secrets(owner_db, make_tenant) -> None:  # type: ignore[no-untyped-def]
    import pytest
    from sqlalchemy import text

    from app.modules.notifications import service as notify_service
    from app.platform.ports.ports import NotifyRequest

    t = make_tenant(slug="log-t")
    with pytest.raises(ValueError):
        notify_service.request_notification(
            owner_db,
            NotifyRequest(
                channel="email",
                to_ref="x",
                template="t",
                locale="en",
                context_refs={"diagnosis": "caries"},
                tenant_id=t.id,
            ),
        )
    owner_db.execute(text("SELECT 1"))
