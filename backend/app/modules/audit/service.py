"""Audit service: append + chain verification. Reading audit is itself
audited by the caller (API layer appends `audit.read` — no recursion: the
read-of-read is recorded as a single entry with resource=audit stream).
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.modules.audit.models import AuditEvent
from app.platform import ids
from app.platform.time import UTC

GENESIS = "0" * 64


def _canonical(
    *,
    occurred_at: datetime,
    tenant_id: uuid.UUID,
    actor_type: str,
    actor_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    prev_hash: str,
) -> str:
    body = "|".join(
        [
            occurred_at.isoformat(),
            str(tenant_id),
            actor_type,
            actor_id,
            action,
            resource_type,
            resource_id,
            prev_hash,
        ]
    )
    return hashlib.sha256(body.encode()).hexdigest()


def append(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_type: str,
    actor_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    encounter_id: str | None = None,
    request_id: str | None = None,
    reason: str | None = None,
    before_ref: str | None = None,
    after_hash: str | None = None,
    result: str = "ok",
    occurred_at: datetime | None = None,
) -> AuditEvent:
    at = occurred_at or datetime.now(UTC)
    day = at.date().isoformat()
    last = db.execute(
        select(AuditEvent.event_hash)
        .where(AuditEvent.tenant_id == tenant_id, AuditEvent.chain_day == day)
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    prev = last or GENESIS
    event = AuditEvent(
        id=ids.uuid7(),
        occurred_at=at,
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        encounter_id=encounter_id,
        request_id=request_id,
        reason=reason,
        before_ref=before_ref,
        after_hash=after_hash,
        result=result,
        chain_day=day,
        prev_hash=prev,
        event_hash=_canonical(
            occurred_at=at, tenant_id=tenant_id, actor_type=actor_type,
            actor_id=actor_id, action=action, resource_type=resource_type,
            resource_id=str(resource_id), prev_hash=prev,
        ),
    )
    db.add(event)
    return event


def verify_chain(db: DBSession, *, tenant_id: uuid.UUID, day: str) -> bool:
    rows = db.execute(
        select(AuditEvent)
        .where(AuditEvent.tenant_id == tenant_id, AuditEvent.chain_day == day)
        .order_by(AuditEvent.occurred_at, AuditEvent.id)
    ).scalars().all()
    prev = GENESIS
    for row in rows:
        if row.prev_hash != prev:
            return False
        if row.event_hash != _canonical(
            occurred_at=row.occurred_at, tenant_id=row.tenant_id,
            actor_type=row.actor_type, actor_id=row.actor_id, action=row.action,
            resource_type=row.resource_type, resource_id=row.resource_id,
            prev_hash=row.prev_hash,
        ):
            return False
        prev = row.event_hash
    return True
