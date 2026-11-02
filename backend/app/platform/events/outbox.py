"""Transactional outbox. Rows are written in the SAME transaction as the
business operation that emits them (atomic publish). A relay/worker claims
rows with SELECT ... FOR UPDATE SKIP LOCKED, dispatches to handlers, retries
with bounded backoff, and parks poison events in dead-letter.

Only domain-meaningful events (see P0.5 §29). No CRUD-for-everything.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import JSON, TIMESTAMP, BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base
from app.platform.time import UTC

MAX_ATTEMPTS = 8


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    type: Mapped[str] = mapped_column(String(120), nullable=False)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    aggregate: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(80), nullable=False)
    # References only (IDs + status labels). NEVER clinical payloads.
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_outbox_status_next", "status", "next_attempt_at"),
        Index("ix_outbox_tenant", "tenant_id"),
    )


PENDING = "pending"
SENT = "sent"
FAILED = "failed"
DEAD = "dead"


def backoff_for_attempt(attempt: int) -> timedelta:
    # 30s, 2m, 8m, 30m, 2h, 8h, 24h — bounded by MAX_ATTEMPTS.
    minutes = [0.5, 2, 8, 30, 120, 480, 1440][min(attempt, 6)]
    return timedelta(minutes=minutes)
