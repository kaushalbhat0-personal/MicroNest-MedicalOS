"""Worker entrypoint: `python -m app.platform.events.worker`.

Polls the outbox and dispatches to registered handlers. Handlers are
registered in app wiring (main.py), never here — this module stays generic.
"""
import time

from app.platform.config import get_settings
from app.platform.db import make_session_factory, scoped_transaction
from app.platform.events.service import process_batch
from app.platform.logging_setup import configure_root_logging, get_logger

log = get_logger(__name__)


def build_handlers(settings):  # type: ignore[no-untyped-def]
    from app.platform.adapters.dev_adapters import DevNotifyAdapter

    handlers = {}

    def _notify(event):  # type: ignore[no-untyped-def]
        adapter = DevNotifyAdapter(settings)
        from app.platform.ports.ports import NotifyRequest

        req = NotifyRequest(
            channel=str(event.payload.get("channel", "in_app")),
            to_ref=str(event.payload.get("to_ref", "")),
            template=str(event.payload.get("template", "")),
            locale=str(event.payload.get("locale", "en")),
            context_refs={
                k: str(v) for k, v in dict(event.payload.get("context_refs", {})).items()
            },
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
