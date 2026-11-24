"""Clinics service: locations within a tenant. P2+ anchors rooms, chairs,
and queue tokens here (ADR-023)."""

from __future__ import annotations

import uuid
from datetime import datetime, time

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DBSession

from app.modules.clinics.models import Location, LocationWorkingHours
from app.modules.tenancy.models import Tenant
from app.platform import ids
from app.platform.errors import ConflictError, NotFoundError, ValidationError
from app.platform.time import UTC

MIN_SLOT = 5
MAX_SLOT = 480


def _now() -> datetime:
    return datetime.now(UTC)


def create_location(
    db: DBSession,
    *,
    tenant: Tenant,
    name: str,
    timezone: str = "Asia/Kolkata",
    enforce_capacity: bool = True,
) -> Location:
    if db.execute(
        select(Location).where(Location.tenant_id == tenant.id, Location.name == name)
    ).scalar_one_or_none():
        raise ConflictError("location name already exists in tenant")
    if enforce_capacity:
        from app.modules.subscriptions import enforcement as enf

        enf.assert_capacity(
            db,
            tenant_id=tenant.id,
            entitlement_key="max_locations",
            delta=1,
        )
    now = _now()
    loc = Location(
        id=ids.uuid7(),
        tenant_id=tenant.id,
        name=name,
        timezone=timezone,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(loc)
    return loc


def set_location_active(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    is_active: bool,
    enforce_capacity: bool = True,
) -> Location:
    """Activate or deactivate a location. Deactivation releases capacity.

    Historical location rows and related records are retained. Reactivation
    requires available location capacity.
    """
    loc = get_location(db, tenant_id=tenant_id, location_id=location_id)
    if loc.is_active == is_active:
        return loc
    if is_active and enforce_capacity:
        from app.modules.subscriptions import enforcement as enf

        enf.assert_capacity(
            db,
            tenant_id=tenant_id,
            entitlement_key="max_locations",
            delta=1,
        )
    loc.is_active = is_active
    loc.updated_at = _now()
    return loc


def list_locations(db: DBSession, *, tenant_id: uuid.UUID) -> list[Location]:
    return list(
        db.execute(select(Location).where(Location.tenant_id == tenant_id).order_by(Location.name))
        .scalars()
        .all()
    )


def get_location(db: DBSession, *, tenant_id: uuid.UUID, location_id: uuid.UUID) -> Location:
    loc = db.get(Location, location_id)
    if loc is None or loc.tenant_id != tenant_id:
        # Same-tenant miss vs cross-tenant probe are indistinguishable: 404.
        raise NotFoundError("location not found")
    return loc


def list_working_hours(
    db: DBSession, *, tenant_id: uuid.UUID, location_id: uuid.UUID
) -> list[LocationWorkingHours]:
    get_location(db, tenant_id=tenant_id, location_id=location_id)
    return list(
        db.execute(
            select(LocationWorkingHours)
            .where(
                LocationWorkingHours.tenant_id == tenant_id,
                LocationWorkingHours.location_id == location_id,
            )
            .order_by(LocationWorkingHours.weekday)
        )
        .scalars()
        .all()
    )


def replace_working_hours(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    windows: list[dict[str, object]],
) -> list[LocationWorkingHours]:
    """Replace the full week for a location. Empty list clears hours."""
    get_location(db, tenant_id=tenant_id, location_id=location_id)
    seen: set[int] = set()
    normalized: list[tuple[int, time, time, int]] = []
    for w in windows:
        raw_weekday = w["weekday"]
        if not isinstance(raw_weekday, int):
            raise ValidationError("weekday must be an integer")
        weekday = raw_weekday
        if weekday < 0 or weekday > 6:
            raise ValidationError("weekday must be 0 (Mon) through 6 (Sun)")
        if weekday in seen:
            raise ValidationError("duplicate weekday in working hours")
        seen.add(weekday)
        start = w["start_local"]
        end = w["end_local"]
        if not isinstance(start, time) or not isinstance(end, time):
            raise ValidationError("start_local and end_local must be times")
        if end <= start:
            raise ValidationError("end_local must be after start_local")
        raw_slot = w.get("slot_minutes", 30)
        if not isinstance(raw_slot, int):
            raise ValidationError("slot_minutes must be an integer")
        slot = raw_slot
        if not (MIN_SLOT <= slot <= MAX_SLOT):
            raise ValidationError("slot_minutes must be between 5 and 480")
        normalized.append((weekday, start, end, slot))
    db.execute(
        delete(LocationWorkingHours).where(
            LocationWorkingHours.tenant_id == tenant_id,
            LocationWorkingHours.location_id == location_id,
        )
    )
    now = _now()
    rows: list[LocationWorkingHours] = []
    for weekday, start_local, end_local, slot_minutes in normalized:
        row = LocationWorkingHours(
            id=ids.uuid7(),
            tenant_id=tenant_id,
            location_id=location_id,
            weekday=weekday,
            start_local=start_local,
            end_local=end_local,
            slot_minutes=slot_minutes,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows
