"""Service catalog domain: CRUD, validation, global visibility.

Note: service_catalog is global and never truncated between tests, so every
test uses unique codes.
"""

from __future__ import annotations

import uuid

import pytest

from app.modules.billing import service_catalog as catalog
from app.platform.errors import ConflictError, NotFoundError, ValidationError


def _code(prefix: str = "svc") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _create(db, **kw):  # type: ignore[no-untyped-def]
    args = {"code": _code(), "display": "Consultation", "default_rate": "500.00"}
    args.update(kw)
    return catalog.create_service(db, **args)


def test_create_read_update_lifecycle(owner_db) -> None:  # type: ignore[no-untyped-def]
    code = _code("consult")
    item = _create(owner_db, code=code, tax_rate="18", hsn_sac="9983")
    assert item.code == code
    assert item.is_active is True
    fetched = catalog.get_service(owner_db, item_id=item.id)
    assert fetched.id == item.id
    assert catalog.get_service_by_code(owner_db, code=code.upper()).id == item.id
    updated = catalog.update_service(
        owner_db, item_id=item.id, display="Follow-up", default_rate="250.00"
    )
    assert updated.display == "Follow-up"
    assert str(updated.default_rate) == "250.00"
    # Code is identity: no code param exists and the stored code never changes.
    assert updated.code == code


def test_duplicate_code_rejected(owner_db) -> None:  # type: ignore[no-untyped-def]
    code = _code("xray")
    _create(owner_db, code=code)
    with pytest.raises(ConflictError):
        _create(owner_db, code=code.upper())  # normalized duplicate
    with pytest.raises(ConflictError):
        _create(owner_db, code=f"  {code}  ")


def test_validation_boundaries(owner_db) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationError):
        _create(owner_db, code="  ")
    with pytest.raises(ValidationError):
        _create(owner_db, code=_code(), display="  ")
    with pytest.raises(ValidationError):
        _create(owner_db, code=_code(), default_rate="-1")
    with pytest.raises(ValidationError):
        _create(owner_db, code=_code(), default_rate=19.99)  # float rejected
    with pytest.raises(ValidationError):
        _create(owner_db, code=_code(), currency="USD")
    with pytest.raises(ValidationError):
        _create(owner_db, code=_code(), tax_rate="101")
    with pytest.raises(ValidationError):
        _create(owner_db, code=_code(), hsn_sac="x" * 17)
    with pytest.raises(NotFoundError):
        catalog.get_service(owner_db, item_id=uuid.uuid4())
    with pytest.raises(NotFoundError):
        catalog.get_service_by_code(owner_db, code="nope-missing")


def test_activate_deactivate_idempotent(owner_db) -> None:  # type: ignore[no-untyped-def]
    item = _create(owner_db, code=_code("clean"))
    off = catalog.set_active(owner_db, item_id=item.id, is_active=False)
    assert off.is_active is False
    again = catalog.set_active(owner_db, item_id=item.id, is_active=False)
    assert again.is_active is False  # no-op success
    on = catalog.set_active(owner_db, item_id=item.id, is_active=True)
    assert on.is_active is True


def test_list_filters_and_keyset_pagination(owner_db) -> None:  # type: ignore[no-untyped-def]
    prefix = f"pg-{uuid.uuid4().hex[:6]}"
    for suffix in ("b-exam", "a-clean", "c-xray"):
        _create(owner_db, code=f"{prefix}-{suffix}")
    catalog.set_active(
        owner_db,
        item_id=catalog.get_service_by_code(owner_db, code=f"{prefix}-c-xray").id,
        is_active=False,
    )
    page1, cursor = catalog.list_services(owner_db, search=prefix, limit=2)
    assert [i.code for i in page1] == [f"{prefix}-a-clean", f"{prefix}-b-exam"]
    assert cursor is not None
    page2, cursor2 = catalog.list_services(
        owner_db, search=prefix, limit=2, cursor=cursor
    )
    assert [i.code for i in page2] == [f"{prefix}-c-xray"]
    assert cursor2 is None
    active_only, _ = catalog.list_services(owner_db, search=prefix, active=True)
    assert {i.code for i in active_only} == {f"{prefix}-a-clean", f"{prefix}-b-exam"}
    inactive_only, _ = catalog.list_services(owner_db, search=prefix, active=False)
    assert [i.code for i in inactive_only] == [f"{prefix}-c-xray"]
