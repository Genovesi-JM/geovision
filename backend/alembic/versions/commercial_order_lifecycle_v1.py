"""Add provider-independent commercial and service-order lifecycle state.

Revision ID: commercial_order_lifecycle_v1
Revises: first_party_catalog_v1
"""

from __future__ import annotations

from datetime import datetime, timezone
import json

from alembic import op
import sqlalchemy as sa


revision = "commercial_order_lifecycle_v1"
down_revision = "first_party_catalog_v1"
branch_labels = None
depends_on = None


_FULFILMENT_FROM_LEGACY = {
    "pending": "DRAFT",
    "created": "CONFIRMED",
    "awaiting_payment": "CONFIRMED",
    "paid": "PAID",
    "processing": "PROCESSING",
    "dispatched": "IN_PROGRESS",
    "assigned": "ASSIGNED",
    "in_progress": "IN_PROGRESS",
    "delivered": "DELIVERED",
    "completed": "COMPLETED",
    "refunded": "COMPLETED",
    "partially_refunded": "COMPLETED",
    "cancelled": "CANCELLED",
    "failed": "FAILED",
}

_PAYMENT_FROM_LEGACY = {
    "paid": "PAID",
    "processing": "PAID",
    "dispatched": "PAID",
    "assigned": "PAID",
    "in_progress": "PAID",
    "delivered": "PAID",
    "completed": "PAID",
    "refunded": "REFUNDED",
    "partially_refunded": "PARTIALLY_REFUNDED",
    "cancelled": "CANCELLED",
    "failed": "FAILED",
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _loads(value: object) -> dict:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _add_order_columns() -> None:
    existing = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("orders")
    }
    compatibility_columns = {
        "company_id": sa.Column("company_id", sa.String(length=36), nullable=True),
        "site_id": sa.Column("site_id", sa.String(length=36), nullable=True),
    }
    missing_compatibility = [
        column for name, column in compatibility_columns.items() if name not in existing
    ]
    if missing_compatibility:
        with op.batch_alter_table("orders") as batch:
            for column in missing_compatibility:
                batch.add_column(column)

    with op.batch_alter_table("orders") as batch:
        batch.add_column(sa.Column("organization_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("workspace_id", sa.String(length=36), nullable=True))
        batch.add_column(
            sa.Column("order_type", sa.String(length=30), nullable=False, server_default="MIXED")
        )
        batch.add_column(
            sa.Column(
                "fulfilment_status", sa.String(length=30), nullable=False, server_default="DRAFT"
            )
        )
        batch.add_column(
            sa.Column("payment_status", sa.String(length=30), nullable=False, server_default="PENDING")
        )
        batch.add_column(sa.Column("previous_fulfilment_status", sa.String(length=30), nullable=True))
        batch.add_column(
            sa.Column("lifecycle_version", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(sa.Column("checkout_idempotency_key", sa.String(length=160), nullable=True))
        batch.add_column(sa.Column("confirmed_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("failed_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("on_hold_reason", sa.Text(), nullable=True))
        batch.create_foreign_key(
            "fk_orders_organization_id_companies",
            "companies",
            ["organization_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_orders_workspace_id_accounts",
            "accounts",
            ["workspace_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_check_constraint(
            "ck_order_type", "order_type IN ('PHYSICAL', 'SERVICE', 'MONITORING', 'MIXED')"
        )
        batch.create_check_constraint(
            "ck_order_fulfilment_status",
            "fulfilment_status IN ('DRAFT', 'QUOTED', 'CONFIRMED', "
            "'PAYMENT_AUTHORIZED', 'PAID', 'SCHEDULING', 'ASSIGNED', "
            "'IN_PROGRESS', 'DATA_UPLOADED', 'PROCESSING', 'QA_REVIEW', "
            "'RESULTS_READY', 'DELIVERED', 'COMPLETED', 'CANCELLED', "
            "'FAILED', 'NEEDS_REFLIGHT', 'ON_HOLD')",
        )
        batch.create_check_constraint(
            "ck_order_payment_status",
            "payment_status IN ('NOT_REQUIRED', 'PENDING', 'AUTHORIZED', 'PAID', "
            "'FAILED', 'CANCELLED', 'PARTIALLY_REFUNDED', 'REFUNDED')",
        )
        batch.create_check_constraint("ck_order_lifecycle_version", "lifecycle_version > 0")
    op.create_index("ix_orders_organization_id", "orders", ["organization_id"], unique=False)
    op.create_index("ix_orders_workspace_id", "orders", ["workspace_id"], unique=False)
    op.create_index("ix_orders_order_type", "orders", ["order_type"], unique=False)
    op.create_index("ix_orders_fulfilment_status", "orders", ["fulfilment_status"], unique=False)
    op.create_index("ix_orders_payment_status", "orders", ["payment_status"], unique=False)
    op.create_index(
        "ix_orders_checkout_idempotency_key",
        "orders",
        ["checkout_idempotency_key"],
        unique=True,
    )


def _add_order_item_columns() -> None:
    existing = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("order_items")
    }
    compatibility_columns = {
        "product_type": sa.Column("product_type", sa.String(length=30), nullable=True),
        "tax_rate": sa.Column("tax_rate", sa.Numeric(5, 4), nullable=True, server_default="0.14"),
        "tax_amount": sa.Column("tax_amount", sa.Numeric(12, 2), nullable=True, server_default="0"),
        "status": sa.Column("status", sa.String(length=30), nullable=True, server_default="pending"),
        "scheduled_date": sa.Column("scheduled_date", sa.DateTime(), nullable=True),
    }
    missing_compatibility = [
        column for name, column in compatibility_columns.items() if name not in existing
    ]
    if missing_compatibility:
        with op.batch_alter_table("order_items") as batch:
            for column in missing_compatibility:
                batch.add_column(column)

    with op.batch_alter_table("order_items") as batch:
        batch.add_column(sa.Column("catalog_item_id", sa.String(length=50), nullable=True))
        batch.add_column(sa.Column("catalog_item_type", sa.String(length=30), nullable=True))
        batch.add_column(
            sa.Column("currency", sa.String(length=5), nullable=False, server_default="AOA")
        )
        batch.add_column(
            sa.Column("pricing_snapshot_json", sa.Text(), nullable=False, server_default="{}")
        )
        batch.add_column(
            sa.Column("fulfilment_hints_json", sa.Text(), nullable=False, server_default="{}")
        )
        batch.add_column(
            sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0")
        )
        batch.create_foreign_key(
            "fk_order_items_catalog_item_id",
            "catalog_items",
            ["catalog_item_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_check_constraint(
            "ck_order_item_discount_nonnegative", "discount_amount >= 0"
        )
    op.create_index(
        "ix_order_items_catalog_item_id", "order_items", ["catalog_item_id"], unique=False
    )


def _add_payment_columns() -> None:
    with op.batch_alter_table("payments") as batch:
        batch.add_column(sa.Column("organization_id", sa.String(length=36), nullable=True))
        batch.add_column(
            sa.Column("refunded_amount", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("authorized_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("completed_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("failed_at", sa.DateTime(), nullable=True))
        batch.create_foreign_key(
            "fk_payments_organization_id_companies",
            "companies",
            ["organization_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_check_constraint("ck_payment_amount_positive", "amount > 0")
        batch.create_check_constraint(
            "ck_payment_refunded_nonnegative", "refunded_amount >= 0"
        )
    op.create_index(
        "ix_payments_organization_id", "payments", ["organization_id"], unique=False
    )


def _create_webhook_ledger() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "payment_webhook_events" in tables:
        columns = {
            column["name"]
            for column in inspector.get_columns("payment_webhook_events")
        }
        if "event_id" not in columns:
            # The enterprise prototype persisted complete provider payloads.
            # Preserve those historical rows without making that unsafe shape
            # the contract for any new notification.
            if "legacy_payment_webhook_events" in tables:
                raise RuntimeError(
                    "Both canonical and legacy payment webhook tables exist; "
                    "manual reconciliation is required before migration"
                )
            op.rename_table("payment_webhook_events", "legacy_payment_webhook_events")
        else:
            return
    op.create_table(
        "payment_webhook_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("event_id", sa.String(length=200), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("signature_verified", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("provider_reference", sa.String(length=200), nullable=True),
        sa.Column("payment_id", sa.String(length=36), nullable=True),
        sa.Column("order_id", sa.String(length=36), nullable=True),
        sa.Column("provider_status", sa.String(length=50), nullable=True),
        sa.Column("outcome", sa.String(length=30), nullable=False, server_default="RECEIVED"),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "outcome IN ('RECEIVED', 'PROCESSED', 'IGNORED')",
            name="ck_payment_webhook_outcome",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "event_id", name="uq_payment_webhook_provider_event"),
    )
    op.create_index(
        "ix_payment_webhook_ledger_order_id",
        "payment_webhook_events",
        ["order_id"],
        unique=False,
    )
    op.create_index(
        "ix_payment_webhook_ledger_payment_id",
        "payment_webhook_events",
        ["payment_id"],
        unique=False,
    )


def _backfill() -> None:
    connection = op.get_bind()
    now = _now()
    orders = connection.execute(
        sa.text(
            "SELECT id, company_id, status, currency, created_at, updated_at FROM orders"
        )
    ).mappings()
    for row in orders:
        legacy = str(row["status"] or "pending").lower()
        organization_id = row["company_id"]
        if organization_id and not connection.execute(
            sa.text("SELECT 1 FROM companies WHERE id = :id"), {"id": organization_id}
        ).first():
            organization_id = None
        payment_row = connection.execute(
            sa.text(
                "SELECT status FROM payments WHERE order_id = :order_id "
                "ORDER BY updated_at DESC, id DESC LIMIT 1"
            ),
            {"order_id": row["id"]},
        ).first()
        payment_status = _PAYMENT_FROM_LEGACY.get(legacy, "PENDING")
        if payment_row:
            payment_status = {
                "processing": "AUTHORIZED",
                "completed": "PAID",
                "failed": "FAILED",
                "cancelled": "CANCELLED",
                "partially_refunded": "PARTIALLY_REFUNDED",
                "refunded": "REFUNDED",
            }.get(str(payment_row[0] or "").lower(), payment_status)
        connection.execute(
            sa.text(
                "UPDATE orders SET organization_id = :organization_id, "
                "fulfilment_status = :fulfilment_status, payment_status = :payment_status, "
                "confirmed_at = :confirmed_at WHERE id = :id"
            ),
            {
                "id": row["id"],
                "organization_id": organization_id,
                "fulfilment_status": _FULFILMENT_FROM_LEGACY.get(legacy, "DRAFT"),
                "payment_status": payment_status,
                "confirmed_at": (
                    row["created_at"] or now
                    if legacy not in {"pending"}
                    else None
                ),
            },
        )

    items = connection.execute(
        sa.text(
            "SELECT oi.id, oi.order_id, oi.product_id, oi.sku, oi.name, "
            "oi.product_type, oi.unit_price, oi.qty, oi.line_total, oi.tax_rate, "
            "oi.tax_amount, oi.scheduled_date, o.currency "
            "FROM order_items oi JOIN orders o ON o.id = oi.order_id"
        )
    ).mappings()
    order_types: dict[str, set[str]] = {}
    for row in items:
        catalog = None
        if row["product_id"]:
            catalog = connection.execute(
                sa.text(
                    "SELECT id, code, name, item_type, price_model, fulfilment_type, "
                    "requires_site, requires_scheduling, duration_hours "
                    "FROM catalog_items WHERE id = :reference OR legacy_source_id = :reference "
                    "ORDER BY CASE WHEN id = :reference THEN 0 ELSE 1 END LIMIT 1"
                ),
                {"reference": row["product_id"]},
            ).mappings().first()
        item_type = (
            catalog["item_type"]
            if catalog
            else (
                "PHYSICAL_PRODUCT"
                if str(row["product_type"] or "").lower() in {"hardware", "physical", "physical_product"}
                else "SERVICE"
            )
        )
        order_types.setdefault(row["order_id"], set()).add(item_type)
        snapshot = {
            "catalog_item_id": catalog["id"] if catalog else None,
            "code": catalog["code"] if catalog else row["sku"],
            "name": catalog["name"] if catalog else row["name"],
            "item_type": item_type,
            "price_model": catalog["price_model"] if catalog else "FIXED",
            "currency": row["currency"] or "AOA",
            "unit_amount": int(row["unit_price"] or 0),
            "quantity": int(row["qty"] or 0),
            "tax_rate": float(row["tax_rate"] or 0),
            "captured_at": now.isoformat(),
            "migrated": True,
        }
        hints = {
            "fulfilment_type": catalog["fulfilment_type"] if catalog else None,
            "requires_site": bool(catalog["requires_site"]) if catalog else False,
            "requires_scheduling": bool(catalog["requires_scheduling"]) if catalog else False,
            "duration_hours": catalog["duration_hours"] if catalog else None,
        }
        connection.execute(
            sa.text(
                "UPDATE order_items SET catalog_item_id = :catalog_item_id, "
                "catalog_item_type = :item_type, currency = :currency, "
                "pricing_snapshot_json = :snapshot, fulfilment_hints_json = :hints "
                "WHERE id = :id"
            ),
            {
                "id": row["id"],
                "catalog_item_id": catalog["id"] if catalog else None,
                "item_type": item_type,
                "currency": row["currency"] or "AOA",
                "snapshot": _dumps(snapshot),
                "hints": _dumps(hints),
            },
        )

    for order_id, values in order_types.items():
        if values <= {"PHYSICAL_PRODUCT"}:
            order_type = "PHYSICAL"
        elif values <= {"MONITORING_PLAN"}:
            order_type = "MONITORING"
        elif not values.intersection({"PHYSICAL_PRODUCT", "MONITORING_PLAN"}):
            order_type = "SERVICE"
        else:
            order_type = "MIXED"
        connection.execute(
            sa.text("UPDATE orders SET order_type = :order_type WHERE id = :id"),
            {"id": order_id, "order_type": order_type},
        )

    payments = connection.execute(
        sa.text("SELECT id, company_id, status, updated_at, amount FROM payments")
    ).mappings()
    for row in payments:
        organization_id = row["company_id"]
        if organization_id and not connection.execute(
            sa.text("SELECT 1 FROM companies WHERE id = :id"), {"id": organization_id}
        ).first():
            organization_id = None
        status = str(row["status"] or "").lower()
        connection.execute(
            sa.text(
                "UPDATE payments SET organization_id = :organization_id, "
                "completed_at = :completed_at, failed_at = :failed_at, "
                "refunded_amount = :refunded_amount WHERE id = :id"
            ),
            {
                "id": row["id"],
                "organization_id": organization_id,
                "completed_at": row["updated_at"] if status in {"completed", "partially_refunded", "refunded"} else None,
                "failed_at": row["updated_at"] if status == "failed" else None,
                "refunded_amount": row["amount"] if status == "refunded" else 0,
            },
        )


def _preflight() -> None:
    connection = op.get_bind()
    invalid_payments = connection.execute(
        sa.text("SELECT COUNT(*) FROM payments WHERE amount IS NULL OR amount <= 0")
    ).scalar_one()
    if invalid_payments:
        raise RuntimeError(
            "commercial_order_lifecycle_v1 preflight failed: "
            f"{invalid_payments} payment row(s) have a non-positive amount; "
            "reconcile those rows before retrying"
        )


def upgrade() -> None:
    _preflight()
    _add_order_columns()
    _add_order_item_columns()
    _add_payment_columns()
    _create_webhook_ledger()
    _backfill()


def downgrade() -> None:
    op.drop_index("ix_payment_webhook_ledger_payment_id", table_name="payment_webhook_events")
    op.drop_index("ix_payment_webhook_ledger_order_id", table_name="payment_webhook_events")
    op.drop_table("payment_webhook_events")
    if "legacy_payment_webhook_events" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.rename_table("legacy_payment_webhook_events", "payment_webhook_events")

    op.drop_index("ix_payments_organization_id", table_name="payments")
    with op.batch_alter_table("payments") as batch:
        batch.drop_constraint("ck_payment_refunded_nonnegative", type_="check")
        batch.drop_constraint("ck_payment_amount_positive", type_="check")
        batch.drop_constraint("fk_payments_organization_id_companies", type_="foreignkey")
        batch.drop_column("failed_at")
        batch.drop_column("completed_at")
        batch.drop_column("authorized_at")
        batch.drop_column("refunded_amount")
        batch.drop_column("organization_id")

    op.drop_index("ix_order_items_catalog_item_id", table_name="order_items")
    with op.batch_alter_table("order_items") as batch:
        batch.drop_constraint("ck_order_item_discount_nonnegative", type_="check")
        batch.drop_constraint("fk_order_items_catalog_item_id", type_="foreignkey")
        batch.drop_column("discount_amount")
        batch.drop_column("fulfilment_hints_json")
        batch.drop_column("pricing_snapshot_json")
        batch.drop_column("currency")
        batch.drop_column("catalog_item_type")
        batch.drop_column("catalog_item_id")

    op.drop_index("ix_orders_checkout_idempotency_key", table_name="orders")
    op.drop_index("ix_orders_payment_status", table_name="orders")
    op.drop_index("ix_orders_fulfilment_status", table_name="orders")
    op.drop_index("ix_orders_order_type", table_name="orders")
    op.drop_index("ix_orders_workspace_id", table_name="orders")
    op.drop_index("ix_orders_organization_id", table_name="orders")
    with op.batch_alter_table("orders") as batch:
        batch.drop_constraint("ck_order_lifecycle_version", type_="check")
        batch.drop_constraint("ck_order_payment_status", type_="check")
        batch.drop_constraint("ck_order_fulfilment_status", type_="check")
        batch.drop_constraint("ck_order_type", type_="check")
        batch.drop_constraint("fk_orders_workspace_id_accounts", type_="foreignkey")
        batch.drop_constraint("fk_orders_organization_id_companies", type_="foreignkey")
        batch.drop_column("on_hold_reason")
        batch.drop_column("failed_at")
        batch.drop_column("confirmed_at")
        batch.drop_column("checkout_idempotency_key")
        batch.drop_column("lifecycle_version")
        batch.drop_column("previous_fulfilment_status")
        batch.drop_column("payment_status")
        batch.drop_column("fulfilment_status")
        batch.drop_column("order_type")
        batch.drop_column("workspace_id")
        batch.drop_column("organization_id")
