"""Worker entrypoint: `python -m app.platform.events.worker`.

Polls the outbox and dispatches to registered handlers. Handlers are
registered in app wiring (main.py), never here — this module stays generic.
"""

import time

from app.platform.config import Settings, get_settings
from app.platform.db import make_session_factory, scoped_transaction
from app.platform.events.outbox import OutboxEvent
from app.platform.events.service import Handler, process_batch
from app.platform.logging_setup import configure_root_logging, get_logger

log = get_logger(__name__)


def build_handlers(settings: Settings) -> dict[str, Handler]:
    from app.platform.adapters.dev_adapters import DevNotifyAdapter

    handlers: dict[str, Handler] = {}

    def _notify(event: OutboxEvent) -> None:
        adapter = DevNotifyAdapter(settings)
        from app.platform.ports.ports import NotifyRequest

        payload = event.payload
        raw_refs = payload.get("context_refs", {})
        if isinstance(raw_refs, dict):
            context_refs = {k: str(v) for k, v in dict(raw_refs).items()}
        else:
            context_refs = {}

        req = NotifyRequest(
            channel=str(payload.get("channel", "in_app")),
            to_ref=str(payload.get("to_ref", "")),
            template=str(payload.get("template", "")),
            locale=str(payload.get("locale", "en")),
            context_refs=context_refs,
            tenant_id=event.tenant_id,
        )
        adapter.send(req)

    handlers["notification.requested"] = _notify
    return handlers


def run_forever(poll_seconds: float = 5.0) -> None:
    configure_root_logging()
    settings = get_settings()
    factory = make_session_factory(settings.APP_DATABASE_URL)
    handlers = build_handlers(settings)
    log.info("outbox worker started")
    while True:
        with scoped_transaction(factory) as session:
            done = process_batch(session, handlers)
        if done["sent"] or done["failed"] or done["dead"]:
            log.info("outbox batch processed")
        time.sleep(poll_seconds)


if __name__ == "__main__":
    run_forever()
