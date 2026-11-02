"""Ports: signed access semantics, dev-adapter fail-closed, payload guards."""

import pytest

from app.platform.adapters.dev_adapters import DevNotifyAdapter, LocalStorageAdapter
from app.platform.config import Settings
from app.platform.ports.ports import NotifyRequest, assert_port_safe

SECRET = "test-signing-secret-min-32-chars-ok"


def test_local_storage_roundtrip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    adapter = LocalStorageAdapter(str(tmp_path), SECRET)
    meta = adapter.put(key="t/doc.pdf", data=b"%PDF-1", content_type="application/pdf")
    assert meta.size_bytes == 6 and meta.sha256
    assert adapter.exists(key="t/doc.pdf")
    assert adapter.get(key="t/doc.pdf") == b"%PDF-1"
    adapter.delete(key="t/doc.pdf")
    assert not adapter.exists(key="t/doc.pdf")


def test_signed_access_expiry_and_tamper(tmp_path) -> None:  # type: ignore[no-untyped-def]
    adapter = LocalStorageAdapter(str(tmp_path), SECRET)
    token = adapter.signed_access(key="t/a.pdf", expires_seconds=60)
    assert adapter.verify_signed_access(key="t/a.pdf", token=token)
    assert not adapter.verify_signed_access(key="t/a.pdf", token=token + "x")
    assert not adapter.verify_signed_access(key="t/other.pdf", token=token)
    expired = adapter.signed_access(key="t/a.pdf", expires_seconds=-1)
    assert not adapter.verify_signed_access(key="t/a.pdf", token=expired)


def test_storage_rejects_path_traversal(tmp_path) -> None:  # type: ignore[no-untyped-def]
    adapter = LocalStorageAdapter(str(tmp_path), SECRET)
    with pytest.raises(ValueError):
        adapter.put(key="../evil", data=b"x", content_type="text/plain")


def test_dev_notify_refuses_prod() -> None:
    settings = Settings(
        OWNER_DATABASE_URL="x",
        APP_DATABASE_URL="x",
        JWT_SECRET="s" * 32,
        ENV="prod",
        DEV_NOTIFICATIONS_ALLOW=False,
    )
    with pytest.raises(RuntimeError):
        DevNotifyAdapter(settings)


def test_dev_notify_health_is_false(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(
        OWNER_DATABASE_URL="x",
        APP_DATABASE_URL="x",
        JWT_SECRET="s" * 32,
        ENV="dev",
        DEV_NOTIFICATIONS_ALLOW=True,
    )
    adapter = DevNotifyAdapter(settings)
    assert adapter.health() is False
    result = adapter.send(
        NotifyRequest(
            channel="email",
            to_ref="user-id",
            template="t",
            locale="en",
            context_refs={},
        )
    )
    assert result.accepted


def test_port_guard_blocks_clinical_and_secrets() -> None:
    with pytest.raises(ValueError):
        assert_port_safe({"diagnosis": "x"})
    with pytest.raises(ValueError):
        assert_port_safe({"token": "x"})
    assert_port_safe({"user_id": "u-1", "template": "t"})
