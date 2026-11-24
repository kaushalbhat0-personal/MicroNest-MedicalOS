"""WhatsApp click-to-chat URL helpers — never send."""

import pytest

from app.modules.communications.whatsapp import build_whatsapp_url, normalize_whatsapp_number
from app.platform.errors import ValidationError


def test_normalize_and_build_url() -> None:
    assert normalize_whatsapp_number("+91 98765-43210") == "919876543210"
    url = build_whatsapp_url(phone="+919876543210", message="Hello clinic")
    assert url.startswith("https://wa.me/919876543210?text=")
    assert "Hello" in url


def test_rejects_bad_phone() -> None:
    with pytest.raises(ValidationError):
        normalize_whatsapp_number("123")
    with pytest.raises(ValidationError):
        build_whatsapp_url(phone="", message="x")
