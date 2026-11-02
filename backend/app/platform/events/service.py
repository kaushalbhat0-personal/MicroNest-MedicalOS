"""Outbox service (emit within caller txn) + minimal worker (claim/process)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.platform import ids
from app.platform.events.outbox import (
    DEAD,
    FAILED,
    MAX_ATTEMPTS,
    PENDING,
    SENT,
    OutboxEvent,
    backoff_for_attempt,
)
from app.platform.logging_setup import get_logger
from app.platform.time import UTC

log = get_logger(__name__)

Handler = Callable[[OutboxEvent], None]


def emit(
    session: Session,
    *,
    type: str,
    aggregate: str,
    aggregate_id: str,
    tenant_id: uuid.UUID | None,
    payload: dict[str, object],
) -> OutboxEvent:
    """Must be called inside the caller's transaction — atomic with business writes."""
    from app.platform.ports.ports import assert_port_safe

    assert_port_safe(payload)
    event = OutboxEvent(
        id=ids.uuid7(),
        occurred_at=datetime.now(UTC),
        type=type,
        tenant_id=tenant_id,
        aggregate=aggregate,
        aggregate_id=aggregate_id,
        payload=payload,
        status=PENDING,
        attempts=0,
        next_attempt_at=datetime.now(UTC),
    )
    session.add(event)
    return event


def claim_batch(session: Session, *, limit: int = 25) -> list[OutboxEvent]:
    # Clock boundary evaluated in the DATABASE (statement timestamp): the app
    # host and DB host clocks must never be compared across this boundary.
    # (A Python-side `now` caused missed claims under coarse timer granularity.)
    rows = (
        session.execute(
            select(OutboxEvent)
            .where(
                OutboxEvent.status.in_([PENDING, FAILED]),
                (OutboxEvent.next_attempt_at.is_(None))
                | (OutboxEvent.next_attempt_at <= func.now()),
            )
            .order_by(OutboxEvent.occurred_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )
    return list(rows)


def process_batch(
    session: Session, handlers: dict[str, Handler], *, limit: int = 25
) -> dict[str, int]:
    """Claim + dispatch one batch. Returns counts. Raises nothing."""
    done = {"sent": 0, "failed": 0, "dead": 0}
    for event in claim_batch(session, limit=limit):
        handler = handlers.get(event.type)
        try:
            if handler is None:
                raise RuntimeError(f"no handler for event type {event.type!r}")
            handler(event)
            event.status = SENT
            event.last_error = None
            done["sent"] += 1
        except Exception as exc:  # noqa: BLE001 — worker must never crash the batch
            event.attempts += 1
            event.last_error = str(exc)[:2000]
            if event.attempts >= MAX_ATTEMPTS:
                event.status = DEAD
                done["dead"] += 1
                log.warning("outbox event dead: %s", event.id)
            else:
                event.status = FAILED
                event.next_attempt_at = datetime.now(UTC) + backoff_for_attempt(event.attempts)
                done["failed"] += 1
    session.commit()
    return done
