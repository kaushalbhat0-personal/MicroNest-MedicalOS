"""Clinics service: locations within a tenant. P2+ anchors rooms, chairs,
and queue tokens here (ADR-023)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.modules.clinics.models import Location
from app.modules.tenancy.models import Tenant
from app.platform import ids
from app.platform.errors import ConflictError, NotFoundError
from app.platform.time import UTC


def _now() -> datetime:
    return datetime.now(UTC)


def create_location(
    db: DBSession, *, tenant: Tenant, name: str, timezone: str = "Asia/Kolkata"
) -> Location:
    if db.execute(
        select(Location).where(Location.tenant_id == tenant.id, Location.name == name)
    ).scalar_one_or_none():
        raise ConflictError("location name already exists in tenant")
    now = _now()
    loc = Location(
        id=ids.uuid7(), tenant_id=tenant.id, name=name, timezone=timezone,
        is_active=True, created_at=now, updated_at=now,
    )
    db.add(loc)
    return loc


def list_locations(db: DBSession, *, tenant_id: uuid.UUID) -> list[Location]:
    return list(
        db.execute(
            select(Location).where(Location.tenant_id == tenant_id).order_by(Location.name)
        ).scalars().all()
    )


def get_location(db: DBSession, *, tenant_id: uuid.UUID, location_id: uuid.UUID) -> Location:
    loc = db.get(Location, location_id)
    if loc is None or loc.tenant_id != tenant_id:
        # Same-tenant miss vs cross-tenant probe are indistinguishable: 404.
        raise NotFoundError("location not found")
    return loc
