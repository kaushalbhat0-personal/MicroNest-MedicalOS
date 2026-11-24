"""User-initiated WhatsApp click-to-chat helpers.

Never sends messages. Never claims delivery. Staff must confirm outcomes
separately via communication logs.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from app.platform.errors import ValidationError

_DIGITS = re.compile(r"\D+")


def normalize_whatsapp_number(phone: str | None) -> str:
    """Return digits-only international number suitable for wa.me.

    Accepts ``+91…`` or bare digits. Rejects short / nonsense values.
    """
    raw = (phone or "").strip()
    if not raw:
        raise ValidationError("phone number required")
    digits = _DIGITS.sub("", raw)
    if raw.startswith("+") or (len(digits) >= 10 and not digits.startswith("0")):
        pass
    if len(digits) < 7 or len(digits) > 15:
        raise ValidationError("invalid phone number for WhatsApp")
    if not digits.isdigit():
        raise ValidationError("invalid phone number for WhatsApp")
    return digits


def build_whatsapp_url(*, phone: str, message: str | None = None) -> str:
    """Build ``https://wa.me/<digits>?text=…``. Does not open or send."""
    digits = normalize_whatsapp_number(phone)
    base = f"https://wa.me/{digits}"
    text = (message or "").strip()
    if not text:
        return base
    if len(text) > 500:
        raise ValidationError("WhatsApp prefill message too long")
    return f"{base}?text={quote(text)}"
