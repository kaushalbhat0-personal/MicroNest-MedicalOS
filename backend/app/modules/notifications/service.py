"""Notifications P1: request API over the outbox. No templates, no provider
fan-out yet (P5). Payloads carry references only — enforced by assert_port_safe.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session as DBSession

from app.platform.events import service as outbox
from app.platform.ports.ports import NotifyRequest, assert_port_safe


def request_notification(
    db: DBSession,
    request: NotifyRequest,
) -> None:
    assert_port_safe(dict(request.context_refs))
    outbox.emit(
        db,
        type="notification.requested",
        aggregate="notification",
        aggregate_id=str(uuid.uuid4()),
        tenant_id=request.tenant_id,
        payload={
            "channel": request.channel,
            "to_ref": request.to_ref,
            "template": request.template,
            "locale": request.locale,
            "context_refs": dict(request.context_refs),
        },
    )
