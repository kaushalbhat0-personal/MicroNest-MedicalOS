"""Notification provider selection. Single selection point — domain code
never branches on deployment.

Providers:
- dev-console : development/test only. Logs intents, health() is always
  False so no release gate can mistake it for a real provider.
- none        : explicitly unavailable. send() raises (fail-closed, never
  silently dropped), health() is False. This is the honest preview/production
  state until a real SES/SMS provider lands post-P7.
"""

from __future__ import annotations

from app.platform.adapters.dev_adapters import DevNotifyAdapter
from app.platform.config import Settings
from app.platform.ports.ports import NotifyRequest, NotifyResult


class NullNotifyAdapter:
    """Explicitly-unavailable provider. Never fails silently."""

    name = "none"

    def __init__(self, settings: Settings | None = None) -> None:
        _ = settings

    def health(self) -> bool:
        return False

    def send(self, request: NotifyRequest) -> NotifyResult:
        raise RuntimeError(
            "notifications are not configured "
            f"(template={request.template} channel={request.channel}); "
            "NOTIFY_PROVIDER=none means delivery is explicitly unavailable"
        )


def build_notify_adapter(settings: Settings) -> DevNotifyAdapter | NullNotifyAdapter:
    if settings.NOTIFY_PROVIDER == "dev-console":
        return DevNotifyAdapter(settings)
    if settings.NOTIFY_PROVIDER == "none":
        return NullNotifyAdapter(settings)
    raise RuntimeError("NOTIFY_PROVIDER must be one of ['dev-console', 'none']")
