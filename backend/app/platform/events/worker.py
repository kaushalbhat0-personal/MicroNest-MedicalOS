"""Worker entrypoint: `python -m app.platform.events.worker [--once]`.

Polls the outbox and dispatches to registered handlers. Handlers are
registered in app wiring (main.py), never here — this module stays generic.

Boot validates deployment configuration first (fail fast): the worker never
starts against a misconfigured preview/production environment. `--once`
processes a single batch and exits — used by smoke tests and release gates.
"""

import argparse
import time

from app.platform.config import Settings, get_settings, require_valid_for_boot
from app.platform.db import make_session_factory, scoped_transaction
from app.platform.events.outbox import OutboxEvent
from app.platform.events.service import Handler, process_batch
from app.platform.logging_setup import configure_root_logging, get_logger

log = get_logger(__name__)


def build_handlers(settings: Settings) -> dict[str, Handler]:
    from app.platform.adapters.notify import build_notify_adapter

    adapter = build_notify_adapter(settings)
    handlers: dict[str, Handler] = {}

    def _notify(event: OutboxEvent) -> None:
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


def run_once(*, limit: int = 25, settings: Settings | None = None) -> dict[str, int]:
    """Process a single outbox batch. Returns sent/failed/dead counts."""
    active = settings or get_settings()
    require_valid_for_boot(active)
    factory = make_session_factory(active.APP_DATABASE_URL)
    handlers = build_handlers(active)
    with scoped_transaction(factory) as session:
        return process_batch(session, handlers, limit=limit)


def run_forever(poll_seconds: float = 5.0) -> None:
    configure_root_logging()
    settings = get_settings()
    require_valid_for_boot(settings)
    factory = make_session_factory(settings.APP_DATABASE_URL)
    handlers = build_handlers(settings)
    from app.platform.adapters.notify import build_notify_adapter as _build

    log.info(
        "outbox worker started",
        extra={
            "deployment": settings.DEPLOYMENT,
            "notify": _build(settings).name,
            "storage": settings.STORAGE_ADAPTER,
        },
    )
    while True:
        with scoped_transaction(factory) as session:
            done = process_batch(session, handlers)
        if done["sent"] or done["failed"] or done["dead"]:
            log.info("outbox batch processed")
        time.sleep(poll_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="worker")
    parser.add_argument("--once", action="store_true", help="one batch, then exit")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args(argv)
    configure_root_logging()
    if args.once:
        try:
            done = run_once(limit=args.limit)
        except RuntimeError as exc:
            # Boot validation: configuration problems, never secret values.
            print(f"worker: refusing to start: {exc}")
            return 2
        except Exception:
            print("worker: database unreachable")
            return 1
        print(f"worker once: {done}")
        return 0 if not done["dead"] else 1
    run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
