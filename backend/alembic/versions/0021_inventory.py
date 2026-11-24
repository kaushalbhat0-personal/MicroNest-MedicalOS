"""0021 generic clinic inventory: catalog, ledger, suppliers, purchase receipts.

Ledger-backed stock. Balances are projections updated with SELECT FOR UPDATE.
Seed role growth for inventory permissions. Not a pharmacy.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0021_inventory"
down_revision: str | Sequence[str] | None = "0020_followups_comms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "hos_app"
SETTING = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

CLINICAL_ADMIN = [
    "encounter.open",
    "encounter.close",
    "encounter.read",
    "clinical.read",
    "clinical.create",
    "prescription.read",
    "prescription.create",
    "prescription.sign",
    "dental.read",
    "dental.record",
    "plan.manage",
]
BILLING_FULL = [
    "billing.read",
    "billing.create",
    "invoice.issue",
    "payment.record",
    "billing.refund",
    "billing.config",
]
COMMS = [
    "followup.read",
    "followup.manage",
    "communication.read",
    "communication.log",
    "communication.consent.manage",
]
INV = [
    "inventory.read",
    "inventory.adjust",
    "inventory.manage",
    "inventory.purchase",
]

ROLE_PERMS = {
    "tenant_admin": [
        "tenant.read",
        "settings.manage",
        "staff.invite",
        "staff.manage",
        "roles.manage",
        "locations.manage",
        "audit.read",
        "appointment.read",
        "appointment.create",
        "appointment.update",
        "patient.read",
        "patient.create",
        "patient.update",
        *CLINICAL_ADMIN,
        *BILLING_FULL,
        *COMMS,
        *INV,
    ],
    "doctor": [
        "tenant.read",
        "appointment.read",
        "appointment.update",
        "patient.read",
        *CLINICAL_ADMIN,
        "billing.read",
        "billing.create",
        *COMMS,
        "inventory.read",
        "inventory.adjust",
    ],
    "receptionist": [
        "tenant.read",
        "appointment.read",
        "appointment.create",
        "appointment.update",
        "patient.read",
        "patient.create",
        "patient.update",
        "encounter.open",
        "encounter.read",
        "billing.read",
        "payment.record",
        *COMMS,
        "inventory.read",
        "inventory.adjust",
    ],
    "nurse": [
        "tenant.read",
        "appointment.read",
        "patient.read",
        "encounter.read",
        "clinical.read",
        "clinical.create",
        "followup.read",
        "followup.manage",
        "communication.read",
        "communication.log",
        "inventory.read",
        "inventory.adjust",
    ],
    "accountant": ["tenant.read", *BILLING_FULL, *INV],
    "staff": ["tenant.read"],
    "patient": [
        "portal.read",
        "portal.appointment.cancel",
        "portal.appointment.book",
    ],
    "platform_admin": [
        "platform.tenant.create",
        "platform.tenant.suspend",
        "platform.health",
    ],
}

PRIOR_ROLE_PERMS = {
    "tenant_admin": [
        "tenant.read",
        "settings.manage",
        "staff.invite",
        "staff.manage",
        "roles.manage",
        "locations.manage",
        "audit.read",
        "appointment.read",
        "appointment.create",
        "appointment.update",
        "patient.read",
        "patient.create",
        "patient.update",
        *CLINICAL_ADMIN,
        *BILLING_FULL,
        *COMMS,
    ],
    "doctor": [
        "tenant.read",
        "appointment.read",
        "appointment.update",
        "patient.read",
        *CLINICAL_ADMIN,
        "billing.read",
        "billing.create",
        *COMMS,
    ],
    "receptionist": [
        "tenant.read",
        "appointment.read",
        "appointment.create",
        "appointment.update",
        "patient.read",
        "patient.create",
        "patient.update",
        "encounter.open",
        "encounter.read",
        "billing.read",
        "payment.record",
        *COMMS,
    ],
    "nurse": [
        "tenant.read",
        "appointment.read",
        "patient.read",
        "encounter.read",
        "clinical.read",
        "clinical.create",
        "followup.read",
        "followup.manage",
        "communication.read",
        "communication.log",
    ],
    "accountant": ["tenant.read"] + BILLING_FULL,
    "staff": ["tenant.read"],
    "patient": [
        "portal.read",
        "portal.appointment.cancel",
        "portal.appointment.book",
    ],
    "platform_admin": [
        "platform.tenant.create",
        "platform.tenant.suspend",
        "platform.health",
    ],
}


def _enums() -> dict[str, postgresql.ENUM]:
    return {
        "inventory_movement_kind": postgresql.ENUM(
            "opening",
            "purchase_receipt",
            "adjustment",
            "consumption",
            "wastage",
            "return",
            "transfer_out",
            "transfer_in",
            name="inventory_movement_kind",
        ),
        "purchase_order_status": postgresql.ENUM(
            "draft",
            "ordered",
            "partially_received",
            "received",
            "cancelled",
            name="purchase_order_status",
        ),
        "goods_receipt_status": postgresql.ENUM(
            "posted", "voided", name="goods_receipt_status"
        ),
    }


RLS_TABLES = (
    "inventory_items",
    "inventory_suppliers",
    "inventory_balances",
    "inventory_movements",
    "purchase_orders",
    "purchase_order_lines",
    "goods_receipts",
    "goods_receipt_lines",
)


def upgrade() -> None:
    E = _enums()

    op.create_table(
        "inventory_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("cost_price", sa.Numeric(18, 2), nullable=False),
        sa.Column("reorder_level", sa.Numeric(18, 4), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "sku", name="uq_inv_items_tenant_sku"),
        sa.CheckConstraint("cost_price >= 0", name="ck_inv_items_cost"),
        sa.CheckConstraint("reorder_level >= 0", name="ck_inv_items_reorder"),
    )
    op.create_index("ix_inv_items_tenant", "inventory_items", ["tenant_id"])

    op.create_table(
        "inventory_suppliers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("contact_name", sa.String(200), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("tax_id", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_inv_suppliers_tenant_name"),
    )
    op.create_index("ix_inv_suppliers_tenant", "inventory_suppliers", ["tenant_id"])

    op.create_table(
        "inventory_balances",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity_on_hand", sa.Numeric(18, 4), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["item_id"], ["inventory_items.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "location_id", "item_id", name="uq_inv_balance_location_item"
        ),
        sa.CheckConstraint("quantity_on_hand >= 0", name="ck_inv_balance_nonneg"),
    )
    op.create_index("ix_inv_balances_tenant", "inventory_balances", ["tenant_id"])
    op.create_index("ix_inv_balances_location", "inventory_balances", ["location_id"])

    op.create_table(
        "inventory_movements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", E["inventory_movement_kind"], nullable=False),
        sa.Column("quantity_delta", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 2), nullable=True),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column("reference_type", sa.String(40), nullable=True),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("transfer_group_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recorded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(80), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["item_id"], ["inventory_items.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_inv_movements_idem"),
        sa.CheckConstraint("quantity_delta != 0", name="ck_inv_movement_nonzero"),
    )
    op.create_index("ix_inv_movements_tenant", "inventory_movements", ["tenant_id"])
    op.create_index("ix_inv_movements_location", "inventory_movements", ["location_id"])
    op.create_index("ix_inv_movements_item", "inventory_movements", ["item_id"])
    op.create_index(
        "ix_inv_movements_occurred", "inventory_movements", ["tenant_id", "occurred_at"]
    )

    op.create_table(
        "purchase_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", E["purchase_order_status"], nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ordered_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["supplier_id"], ["inventory_suppliers.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_po_tenant", "purchase_orders", ["tenant_id"])
    op.create_index("ix_po_location", "purchase_orders", ["location_id"])
    op.create_index("ix_po_supplier", "purchase_orders", ["supplier_id"])

    op.create_table(
        "purchase_order_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity_ordered", sa.Numeric(18, 4), nullable=False),
        sa.Column("quantity_received", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 2), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"], ["purchase_orders.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["item_id"], ["inventory_items.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("purchase_order_id", "item_id", name="uq_po_line_item"),
        sa.CheckConstraint("quantity_ordered > 0", name="ck_po_line_qty"),
        sa.CheckConstraint("quantity_received >= 0", name="ck_po_line_recv"),
        sa.CheckConstraint("unit_cost >= 0", name="ck_po_line_cost"),
    )
    op.create_index("ix_po_lines_po", "purchase_order_lines", ["purchase_order_id"])

    op.create_table(
        "goods_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", E["goods_receipt_status"], nullable=False),
        sa.Column("receipt_key", sa.String(80), nullable=False),
        sa.Column("received_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("received_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"], ["purchase_orders.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "receipt_key", name="uq_gr_receipt_key"),
    )
    op.create_index("ix_gr_tenant", "goods_receipts", ["tenant_id"])
    op.create_index("ix_gr_po", "goods_receipts", ["purchase_order_id"])

    op.create_table(
        "goods_receipt_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("goods_receipt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 2), nullable=False),
        sa.Column("movement_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["goods_receipt_id"], ["goods_receipts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["purchase_order_line_id"], ["purchase_order_lines.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["item_id"], ["inventory_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["movement_id"], ["inventory_movements.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("quantity > 0", name="ck_gr_line_qty"),
    )
    op.create_index("ix_gr_lines_receipt", "goods_receipt_lines", ["goods_receipt_id"])

    for table in RLS_TABLES:
        op.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}"))
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY {table}_tenant_isolation ON {table} "
                f"FOR ALL TO {APP_ROLE} USING (tenant_id = {SETTING}) "
                f"WITH CHECK (tenant_id = {SETTING})"
            )
        )

    for name, perms in ROLE_PERMS.items():
        op.execute(
            sa.text(
                "UPDATE roles SET permissions = CAST(:perms AS JSONB) "
                "WHERE tenant_id IS NULL AND name = :name"
            ).bindparams(perms=json.dumps(sorted(perms)), name=name)
        )


def downgrade() -> None:
    for name, perms in PRIOR_ROLE_PERMS.items():
        op.execute(
            sa.text(
                "UPDATE roles SET permissions = CAST(:perms AS JSONB) "
                "WHERE tenant_id IS NULL AND name = :name"
            ).bindparams(perms=json.dumps(sorted(perms)), name=name)
        )

    for table in reversed(RLS_TABLES):
        op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    op.drop_table("goods_receipt_lines")
    op.drop_table("goods_receipts")
    op.drop_table("purchase_order_lines")
    op.drop_table("purchase_orders")
    op.drop_table("inventory_movements")
    op.drop_table("inventory_balances")
    op.drop_table("inventory_suppliers")
    op.drop_table("inventory_items")

    for enum_name in (
        "goods_receipt_status",
        "purchase_order_status",
        "inventory_movement_kind",
    ):
        postgresql.ENUM(name=enum_name).drop(op.get_bind(), checkfirst=True)
