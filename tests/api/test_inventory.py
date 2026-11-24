"""P1.1 generic clinic inventory: ledger, PO receipts, isolation."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

from tests.helpers import login_client, provision_tenant, tenant_headers


def _setup(owner_db, make_owner_user, make_tenant):
    from app.modules.clinics import service as clinics_service

    base = provision_tenant(
        owner_db,
        make_owner_user,
        make_tenant,
        slug=f"inv-{uuid.uuid4().hex[:6]}",
        admin_email=f"inv-{uuid.uuid4().hex[:6]}@example.com",
    )
    loc2 = clinics_service.create_location(
        owner_db, tenant=base["tenant"], name="Branch Clinic"
    )
    owner_db.commit()
    return {**base, "location2": loc2}


def _auth(client, b):
    return login_client(client, email=b["admin"].email), tenant_headers(str(b["tenant"].id))


def test_item_crud_and_duplicate_sku(client, owner_db, make_owner_user, make_tenant):
    b = _setup(owner_db, make_owner_user, make_tenant)
    doc, h = _auth(client, b)
    tid = b["tenant"].id
    created = doc.post(
        f"/api/v1/tenants/{tid}/inventory/items",
        headers=h,
        json={
            "sku": "glove-m",
            "name": "Nitrile Gloves M",
            "category": "consumable",
            "unit": "box",
            "cost_price": "120.00",
            "reorder_level": "10",
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["sku"] == "GLOVE-M"
    dup = doc.post(
        f"/api/v1/tenants/{tid}/inventory/items",
        headers=h,
        json={"sku": "GLOVE-M", "name": "Other"},
    )
    assert dup.status_code == 409


def test_opening_adjust_consume_and_negative_blocked(
    client, owner_db, make_owner_user, make_tenant
):
    b = _setup(owner_db, make_owner_user, make_tenant)
    doc, h = _auth(client, b)
    tid, lid = b["tenant"].id, b["location"].id
    item = doc.post(
        f"/api/v1/tenants/{tid}/inventory/items",
        headers=h,
        json={"sku": "mask-1", "name": "Surgical Mask", "cost_price": "5.00", "reorder_level": "20"},
    ).json()
    open_mv = doc.post(
        f"/api/v1/tenants/{tid}/inventory/opening-stock",
        headers=h,
        json={
            "location_id": str(lid),
            "item_id": item["id"],
            "quantity": "50",
            "unit_cost": "5.00",
            "idempotency_key": "open-1",
        },
    )
    assert open_mv.status_code == 200, open_mv.text
    # Idempotent replay
    again = doc.post(
        f"/api/v1/tenants/{tid}/inventory/opening-stock",
        headers=h,
        json={
            "location_id": str(lid),
            "item_id": item["id"],
            "quantity": "50",
            "idempotency_key": "open-1",
        },
    )
    assert again.status_code == 200
    assert again.json()["id"] == open_mv.json()["id"]

    adj = doc.post(
        f"/api/v1/tenants/{tid}/inventory/adjustments",
        headers=h,
        json={
            "location_id": str(lid),
            "item_id": item["id"],
            "quantity_delta": "-5",
            "reason": "count correction",
        },
    )
    assert adj.status_code == 200

    cons = doc.post(
        f"/api/v1/tenants/{tid}/inventory/consume",
        headers=h,
        json={
            "location_id": str(lid),
            "item_id": item["id"],
            "quantity": "10",
            "reason": "procedure use",
        },
    )
    assert cons.status_code == 200

    bals = doc.get(
        f"/api/v1/tenants/{tid}/inventory/balances?location_id={lid}", headers=h
    ).json()
    assert len(bals) == 1
    assert Decimal(bals[0]["quantity_on_hand"]) == Decimal("35")

    over = doc.post(
        f"/api/v1/tenants/{tid}/inventory/consume",
        headers=h,
        json={
            "location_id": str(lid),
            "item_id": item["id"],
            "quantity": "100",
            "reason": "too much",
        },
    )
    assert over.status_code == 409


def test_purchase_partial_and_full_receipt_idempotent(
    client, owner_db, make_owner_user, make_tenant
):
    b = _setup(owner_db, make_owner_user, make_tenant)
    doc, h = _auth(client, b)
    tid, lid = b["tenant"].id, b["location"].id
    item = doc.post(
        f"/api/v1/tenants/{tid}/inventory/items",
        headers=h,
        json={"sku": "syr-5", "name": "Syringe 5ml", "cost_price": "2.50"},
    ).json()
    supplier = doc.post(
        f"/api/v1/tenants/{tid}/inventory/suppliers",
        headers=h,
        json={"name": "MedSupply Co"},
    ).json()
    po = doc.post(
        f"/api/v1/tenants/{tid}/inventory/purchase-orders",
        headers=h,
        json={
            "location_id": str(lid),
            "supplier_id": supplier["id"],
            "lines": [{"item_id": item["id"], "quantity": "100", "unit_cost": "2.50"}],
        },
    )
    assert po.status_code == 200, po.text
    po_id = po.json()["id"]
    line_id = po.json()["lines"][0]["id"]
    assert (
        doc.post(
            f"/api/v1/tenants/{tid}/inventory/purchase-orders/{po_id}/submit",
            headers=h,
            json={},
        ).status_code
        == 200
    )

    partial = doc.post(
        f"/api/v1/tenants/{tid}/inventory/purchase-orders/{po_id}/receive",
        headers=h,
        json={
            "receipt_key": "gr-partial-1",
            "lines": [{"purchase_order_line_id": line_id, "quantity": "40"}],
        },
    )
    assert partial.status_code == 200, partial.text
    mid = doc.get(
        f"/api/v1/tenants/{tid}/inventory/purchase-orders/{po_id}", headers=h
    ).json()
    assert mid["status"] == "partially_received"

    # Duplicate receipt key returns same receipt
    replay = doc.post(
        f"/api/v1/tenants/{tid}/inventory/purchase-orders/{po_id}/receive",
        headers=h,
        json={
            "receipt_key": "gr-partial-1",
            "lines": [{"purchase_order_line_id": line_id, "quantity": "40"}],
        },
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == partial.json()["id"]

    full = doc.post(
        f"/api/v1/tenants/{tid}/inventory/purchase-orders/{po_id}/receive",
        headers=h,
        json={
            "receipt_key": "gr-final-1",
            "lines": [{"purchase_order_line_id": line_id, "quantity": "60"}],
        },
    )
    assert full.status_code == 200, full.text
    done = doc.get(
        f"/api/v1/tenants/{tid}/inventory/purchase-orders/{po_id}", headers=h
    ).json()
    assert done["status"] == "received"
    bals = doc.get(
        f"/api/v1/tenants/{tid}/inventory/balances?location_id={lid}", headers=h
    ).json()
    assert Decimal(bals[0]["quantity_on_hand"]) == Decimal("100")


def test_transfer_wastage_return_and_dashboard(
    client, owner_db, make_owner_user, make_tenant
):
    b = _setup(owner_db, make_owner_user, make_tenant)
    doc, h = _auth(client, b)
    tid, lid, lid2 = b["tenant"].id, b["location"].id, b["location2"].id
    item = doc.post(
        f"/api/v1/tenants/{tid}/inventory/items",
        headers=h,
        json={"sku": "gauze", "name": "Gauze Pack", "cost_price": "10", "reorder_level": "50"},
    ).json()
    doc.post(
        f"/api/v1/tenants/{tid}/inventory/opening-stock",
        headers=h,
        json={"location_id": str(lid), "item_id": item["id"], "quantity": "30"},
    )
    xfer = doc.post(
        f"/api/v1/tenants/{tid}/inventory/transfers",
        headers=h,
        json={
            "from_location_id": str(lid),
            "to_location_id": str(lid2),
            "item_id": item["id"],
            "quantity": "8",
        },
    )
    assert xfer.status_code == 200, xfer.text
    assert len(xfer.json()) == 2

    waste = doc.post(
        f"/api/v1/tenants/{tid}/inventory/wastage",
        headers=h,
        json={
            "location_id": str(lid),
            "item_id": item["id"],
            "quantity": "2",
            "reason": "expired",
        },
    )
    assert waste.status_code == 200
    ret = doc.post(
        f"/api/v1/tenants/{tid}/inventory/returns",
        headers=h,
        json={
            "location_id": str(lid),
            "item_id": item["id"],
            "quantity": "1",
            "reason": "unused return",
        },
    )
    assert ret.status_code == 200

    dash = doc.get(f"/api/v1/tenants/{tid}/inventory/dashboard", headers=h)
    assert dash.status_code == 200
    body = dash.json()
    assert body["active_items"] >= 1
    assert body["low_stock_count"] >= 1
    assert "stock_valuation" in body


def test_tenant_isolation(client, owner_db, make_owner_user, make_tenant):
    a = _setup(owner_db, make_owner_user, make_tenant)
    b = _setup(owner_db, make_owner_user, make_tenant)
    ca, ha = _auth(client, a)
    item = ca.post(
        f"/api/v1/tenants/{a['tenant'].id}/inventory/items",
        headers=ha,
        json={"sku": "iso-1", "name": "Iso Item"},
    ).json()
    # Cross-tenant get
    r = ca.get(
        f"/api/v1/tenants/{a['tenant'].id}/inventory/items/{item['id']}",
        headers=tenant_headers(str(b["tenant"].id)),
    )
    # Wrong tenant header with A's path should fail match_tenant / authz
    assert r.status_code in (401, 403, 404)
    # Explicit wrong tenant id in path
    r2 = ca.get(
        f"/api/v1/tenants/{b['tenant'].id}/inventory/items/{item['id']}",
        headers=ha,
    )
    assert r2.status_code in (403, 404)


def test_concurrent_consume_does_not_go_negative(
    owner_db, make_owner_user, make_tenant
):
    """Service-level concurrency: FOR UPDATE prevents negative stock."""
    from app.modules.inventory import service as inv
    from app.platform.db import make_session_factory
    from app.platform.errors import ConflictError
    from tests.conftest import TEST_OWNER_URL

    b = _setup(owner_db, make_owner_user, make_tenant)
    tid, lid, actor = b["tenant"].id, b["location"].id, b["admin"].id
    item = inv.create_item(owner_db, tenant_id=tid, sku="race-1", name="Race Item")
    inv.post_opening_stock(
        owner_db,
        tenant_id=tid,
        actor_id=actor,
        location_id=lid,
        item_id=item.id,
        quantity="10",
    )
    owner_db.commit()

    factory = make_session_factory(TEST_OWNER_URL)

    def consume_one(i: int) -> str:
        with factory() as session:
            try:
                inv.consume_stock(
                    session,
                    tenant_id=tid,
                    actor_id=actor,
                    location_id=lid,
                    item_id=item.id,
                    quantity="3",
                    reason=f"race-{i}",
                    idempotency_key=f"race-consume-{uuid.uuid4().hex}",
                )
                session.commit()
                return "ok"
            except ConflictError:
                session.rollback()
                return "conflict"
            except Exception:
                session.rollback()
                raise

    results = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = [pool.submit(consume_one, i) for i in range(6)]
        for fut in as_completed(futs):
            results.append(fut.result())

    assert results.count("ok") == 3
    assert results.count("conflict") == 3
    bal = inv.get_balance(
        owner_db, tenant_id=tid, location_id=lid, item_id=item.id
    )
    assert bal == Decimal("1")
