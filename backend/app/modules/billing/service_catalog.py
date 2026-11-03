"""Service catalog service. Billing-owned charge master (global, no tenant).

Single authority for catalog reads/writes. Catalog rows describe current
billable services; estimates/invoices snapshot values at issue time, so
catalog mutation never rewrites financial history. No destructive delete:
retire via deactivation, since snapshots may reference the entry.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.modules.billing import money as moneylib
from app.modules.billing.models import ServiceCatalogItem
from app.platform import ids
from app.platform.errors import ConflictError, NotFoundError, ValidationError


def _normalize_code(code: str) -> str:
    cleaned = (code or "").strip().lower()
    if not cleaned or len(cleaned) > 40:
        raise ValidationError("service code must be 1-40 characters")
    return cleaned


def get_service(db: DBSession, *, item_id: uuid.UUID) -> ServiceCatalogItem:
    row = db.get(ServiceCatalogItem, item_id)
    if row is None:
        raise NotFoundError("service not found")
    return row


def get_service_by_code(db: DBSession, *, code: str) -> ServiceCatalogItem:
    row = db.execute(
        select(ServiceCatalogItem).where(ServiceCatalogItem.code == _normalize_code(code))
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("service not found")
    return row


def list_services(
    db: DBSession,
    *,
    active: bool | None = None,
    search: str | None = None,
    limit: int = 50,
    cursor: uuid.UUID | None = None,
) -> tuple[list[ServiceCatalogItem], uuid.UUID | None]:
    """Keyset page over (code, id). Global: no tenant filter, ever."""
    q = select(ServiceCatalogItem)
    if active is not None:
        q = q.where(ServiceCatalogItem.is_active.is_(active))
    if search is not None and search.strip():
        like = f"%{search.strip().lower()}%"
        q = q.where(ServiceCatalogItem.code.ilike(like) | ServiceCatalogItem.display.ilike(like))
    if cursor is not None:
        anchor = get_service(db, item_id=cursor)
        q = q.where(
            (ServiceCatalogItem.code > anchor.code)
            | ((ServiceCatalogItem.code == anchor.code) & (ServiceCatalogItem.id > anchor.id))
        )
    capped = min(max(limit, 1), 200)
    rows = list(
        db.execute(q.order_by(ServiceCatalogItem.code, ServiceCatalogItem.id).limit(capped + 1))
        .scalars()
        .all()
    )
    if len(rows) > capped:
        return rows[:-1], rows[-2].id
    return rows, None


def create_service(
    db: DBSession,
    *,
    code: str,
    display: str,
    description: str | None = None,
    default_rate: object = 0,
    currency: str = "INR",
    hsn_sac: str | None = None,
    tax_rate: object = 0,
) -> ServiceCatalogItem:
    """Create a catalog entry. Duplicate codes (post-normalization) are 409."""
    normalized = _normalize_code(code)
    name = (display or "").strip()
    if not name or len(name) > 200:
        raise ValidationError("display name must be 1-200 characters")
    rate = moneylib.ensure_decimal(default_rate, field="default_rate")
    if rate < 0:
        raise ValidationError("default rate must be non-negative")
    moneylib.validate_currency(currency)
    tax = moneylib.ensure_decimal(tax_rate, field="tax_rate")
    if tax < 0 or tax > 100:
        raise ValidationError("tax rate must be between 0 and 100")
    hsn = (hsn_sac or "").strip() or None
    if hsn is not None and len(hsn) > 16:
        raise ValidationError("hsn/sac must be at most 16 characters")
    if (
        db.execute(
            select(ServiceCatalogItem).where(ServiceCatalogItem.code == normalized)
        ).scalar_one_or_none()
        is not None
    ):
        raise ConflictError("service code already exists")
    row = ServiceCatalogItem(
        id=ids.uuid7(),
        code=normalized,
        display=name,
        description=(description or "").strip() or None,
        default_rate=rate,
        currency=currency,
        hsn_sac=hsn,
        tax_rate=tax,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ConflictError("service code already exists") from None
    return row


def update_service(
    db: DBSession,
    *,
    item_id: uuid.UUID,
    display: str | None = None,
    description: str | None = None,
    default_rate: object = None,
    tax_rate: object = None,
    hsn_sac: str | None = None,
    currency: str | None = None,
) -> ServiceCatalogItem:
    """Update editable metadata. Code is identity and never changes."""
    row = get_service(db, item_id=item_id)
    if display is not None:
        name = display.strip()
        if not name or len(name) > 200:
            raise ValidationError("display name must be 1-200 characters")
        row.display = name
    if description is not None:
        desc = description.strip() or None
        if desc is not None and len(desc) > 500:
            raise ValidationError("description must be at most 500 characters")
        row.description = desc
    if default_rate is not None:
        rate = moneylib.ensure_decimal(default_rate, field="default_rate")
        if rate < 0:
            raise ValidationError("default rate must be non-negative")
        row.default_rate = rate
    if tax_rate is not None:
        tax = moneylib.ensure_decimal(tax_rate, field="tax_rate")
        if tax < 0 or tax > 100:
            raise ValidationError("tax rate must be between 0 and 100")
        row.tax_rate = tax
    if hsn_sac is not None:
        hsn = hsn_sac.strip() or None
        if hsn is not None and len(hsn) > 16:
            raise ValidationError("hsn/sac must be at most 16 characters")
        row.hsn_sac = hsn
    if currency is not None:
        moneylib.validate_currency(currency)
        row.currency = currency
    db.flush()
    return row


def set_active(db: DBSession, *, item_id: uuid.UUID, is_active: bool) -> ServiceCatalogItem:
    """Activate/deactivate. Same-state requests are no-op successes."""
    row = get_service(db, item_id=item_id)
    if row.is_active == is_active:
        return row
    row.is_active = is_active
    db.flush()
    return row
