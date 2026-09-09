"""Add the canonical GeoVision first-party catalogue.

Revision ID: first_party_catalog_v1
Revises: invitation_onboarding_v1
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import uuid

from alembic import op
import sqlalchemy as sa


revision = "first_party_catalog_v1"
down_revision = "invitation_onboarding_v1"
branch_labels = None
depends_on = None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _identifier(value: object, default: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(value or default).strip())
    return normalized.strip("_").upper() or default


def _slug(value: object, default: str = "catalog-item") -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value or default).strip().lower())
    return normalized.strip("-") or default


def _loads(value: object, default):
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError):
        return default
    return parsed if isinstance(parsed, type(default)) else default


def _dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sector(value: object) -> str:
    normalized = _identifier(value, "INFRASTRUCTURE")
    return {
        "AGRO": "AGRICULTURE",
        "AGRICULTURE": "AGRICULTURE",
        "LIVESTOCK": "AGRICULTURE",
        "CONSTRUCTION": "INFRASTRUCTURE",
        "INFRASTRUCTURE": "INFRASTRUCTURE",
        "WATER": "INFRASTRUCTURE",
        "ENERGY": "INFRASTRUCTURE",
        "FACILITIES": "INFRASTRUCTURE",
        "COLD_CHAIN": "INFRASTRUCTURE",
        "SOLAR": "INFRASTRUCTURE",
        "DEMINING": "INFRASTRUCTURE",
        "ENVIRONMENT": "ENVIRONMENTAL",
        "ENVIRONMENTAL": "ENVIRONMENTAL",
        "AMBIENTAL": "ENVIRONMENTAL",
        "MINING": "MINING",
        "INDUSTRY": "PORTS_INDUSTRIAL",
        "INDUSTRIAL": "PORTS_INDUSTRIAL",
        "PORT": "PORTS_INDUSTRIAL",
        "PORTS": "PORTS_INDUSTRIAL",
        "PORTS_INDUSTRIAL": "PORTS_INDUSTRIAL",
    }.get(normalized, normalized)


def _item_type(product_type: object, category: object, name: object) -> str:
    product_type_value = str(product_type or "").lower()
    combined = " ".join((product_type_value, str(category or ""), str(name or ""))).lower()
    if product_type_value in {"hardware", "physical", "physical_product"}:
        return "PHYSICAL_PRODUCT"
    if product_type_value in {"subscription", "monitoring_plan"} or "monitor" in combined:
        return "MONITORING_PLAN"
    if "install" in combined:
        return "INSTALLATION"
    if "inspec" in combined:
        return "INSPECTION"
    if "analy" in combined or "anális" in combined or "analise" in combined:
        return "ANALYSIS"
    return "SERVICE"


def _fulfilment_type(item_type: str) -> str:
    return {
        "PHYSICAL_PRODUCT": "PHYSICAL_SHIPMENT",
        "MONITORING_PLAN": "MONITORING_ACTIVATION",
        "INSTALLATION": "FIELD_INSTALLATION",
        "INSPECTION": "FIELD_SERVICE",
        "ANALYSIS": "REMOTE_ANALYSIS",
    }.get(item_type, "FIELD_SERVICE")


def _unique(connection, column: str, value: str) -> str:
    candidate = value
    suffix = 1
    while connection.execute(
        sa.text(f"SELECT 1 FROM catalog_items WHERE {column} = :value"),
        {"value": candidate},
    ).first():
        suffix += 1
        candidate = f"{value[: max(1, 190 - len(str(suffix)))]}-{suffix}"
    return candidate


def _insert(connection, values: dict) -> None:
    connection.execute(
        sa.text(
            """
            INSERT INTO catalog_items
                (id, code, slug, item_type, name, summary, description,
                 category, sectors_json, asset_types_json,
                 customer_content_json, deliverables_json, price_model,
                 currency, unit_amount, pricing_json, availability_status,
                 status, recommendation_triggers_json, metadata_json,
                 image_url, is_featured, requires_site, requires_scheduling,
                 duration_hours, fulfilment_type, installed_product_type,
                 supplier_id, legacy_source, legacy_source_id, published_at,
                 created_by_user_id, updated_by_user_id, created_at, updated_at)
            VALUES
                (:id, :code, :slug, :item_type, :name, :summary, :description,
                 :category, :sectors_json, :asset_types_json,
                 :customer_content_json, :deliverables_json, :price_model,
                 :currency, :unit_amount, :pricing_json, :availability_status,
                 :status, :recommendation_triggers_json, :metadata_json,
                 :image_url, :is_featured, :requires_site,
                 :requires_scheduling, :duration_hours, :fulfilment_type,
                 :installed_product_type, NULL, :legacy_source,
                 :legacy_source_id, :published_at, NULL, NULL,
                 :created_at, :updated_at)
            """
        ),
        values,
    )


def _backfill_shop_products() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, name, slug, description, short_description,
                   product_type, category, execution_type, price, price_usd,
                   price_eur, currency, tax_rate, duration_hours,
                   requires_site, min_area_ha, sectors_json,
                   deliverables_json, image_url, is_active, is_featured,
                   track_inventory, stock_quantity, created_at, updated_at
            FROM shop_products
            ORDER BY id
            """
        )
    ).mappings()
    for row in rows:
        item_type = _item_type(row["product_type"], row["category"], row["name"])
        prices = {
            currency: int(amount)
            for currency, amount in {
                "AOA": row["price"],
                "USD": row["price_usd"],
                "EUR": row["price_eur"],
            }.items()
            if amount is not None and int(amount) > 0
        }
        created_at = row["created_at"] or _now()
        updated_at = row["updated_at"] or created_at
        item_id = str(row["id"])
        if connection.execute(
            sa.text("SELECT 1 FROM catalog_items WHERE id = :id"), {"id": item_id}
        ).first():
            item_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"geovision:catalog:shop:{row['id']}"))
        active = bool(row["is_active"])
        _insert(
            connection,
            {
                "id": item_id,
                "code": _unique(connection, "code", _identifier(f"LEGACY_{row['id']}", "LEGACY_PRODUCT")[:100]),
                "slug": _unique(connection, "slug", str(row["slug"])[:200]),
                "item_type": item_type,
                "name": row["name"],
                "summary": row["short_description"],
                "description": row["description"],
                "category": row["category"],
                "sectors_json": _dumps(sorted({_sector(value) for value in _loads(row["sectors_json"], [])})),
                "asset_types_json": _dumps([_identifier(row["category"], "SITE")]),
                "customer_content_json": _dumps(
                    {
                        "short_description": row["short_description"],
                        "execution_type": row["execution_type"],
                        "minimum_area_hectares": row["min_area_ha"],
                    }
                ),
                "deliverables_json": _dumps(_loads(row["deliverables_json"], [])),
                "price_model": "SUBSCRIPTION" if item_type == "MONITORING_PLAN" else "FIXED",
                "currency": row["currency"] or "AOA",
                "unit_amount": int(row["price"] or 0),
                "pricing_json": _dumps(prices),
                "availability_status": "AVAILABLE" if active else "UNAVAILABLE",
                "status": "PUBLISHED" if active else "ARCHIVED",
                "recommendation_triggers_json": "[]",
                "metadata_json": _dumps(
                    {
                        "legacy": {"source": "shop_products", "id": row["id"]},
                        "tax_rate": float(row["tax_rate"] or 0),
                        "track_inventory": bool(row["track_inventory"]),
                        "stock_quantity": int(row["stock_quantity"] or 0),
                        "min_area_ha": row["min_area_ha"],
                        "execution_type": row["execution_type"],
                    }
                ),
                "image_url": row["image_url"],
                "is_featured": bool(row["is_featured"]),
                "requires_site": bool(row["requires_site"]),
                "requires_scheduling": item_type not in {"PHYSICAL_PRODUCT", "ANALYSIS"},
                "duration_hours": row["duration_hours"],
                "fulfilment_type": _fulfilment_type(item_type),
                "installed_product_type": row["category"] if item_type == "PHYSICAL_PRODUCT" else None,
                "legacy_source": "shop_products",
                "legacy_source_id": row["id"],
                "published_at": updated_at if active else None,
                "created_at": created_at,
                "updated_at": updated_at,
            },
        )


def _backfill_basic_products() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT p.id, p.sku, p.name, p.description, p.brand, p.unit,
                   p.price, p.currency, p.is_active, p.created_at, p.updated_at,
                   c.slug AS category_slug,
                   (SELECT pi.url FROM product_images pi
                    WHERE pi.product_id = p.id
                    ORDER BY pi.is_primary DESC, pi.id LIMIT 1) AS image_url,
                   (SELECT i.qty_on_hand FROM inventory i
                    WHERE i.product_id = p.id LIMIT 1) AS qty_on_hand
            FROM products p
            LEFT JOIN categories c ON c.id = p.category_id
            ORDER BY p.id
            """
        )
    ).mappings()
    for row in rows:
        created_at = row["created_at"] or _now()
        updated_at = row["updated_at"] or created_at
        active = bool(row["is_active"])
        item_id = f"legacy_{row['id']}"[:50]
        if connection.execute(
            sa.text("SELECT 1 FROM catalog_items WHERE id = :id"), {"id": item_id}
        ).first():
            item_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"geovision:catalog:product:{row['id']}"))
        currency = row["currency"] or "AOA"
        price = int(row["price"] or 0)
        _insert(
            connection,
            {
                "id": item_id,
                "code": _unique(connection, "code", _identifier(f"INVENTORY_{row['sku']}", "INVENTORY_PRODUCT")[:100]),
                "slug": _unique(connection, "slug", _slug(f"inventory-{row['sku']}")),
                "item_type": "PHYSICAL_PRODUCT",
                "name": row["name"],
                "summary": str(row["description"] or "")[:500] or None,
                "description": row["description"],
                "category": row["category_slug"],
                "sectors_json": "[]",
                "asset_types_json": "[]",
                "customer_content_json": _dumps({"brand": row["brand"], "unit": row["unit"]}),
                "deliverables_json": "[]",
                "price_model": "FIXED",
                "currency": currency,
                "unit_amount": price,
                "pricing_json": _dumps({currency: price}),
                "availability_status": "AVAILABLE" if active else "UNAVAILABLE",
                "status": "PUBLISHED" if active else "ARCHIVED",
                "recommendation_triggers_json": "[]",
                "metadata_json": _dumps(
                    {
                        "legacy": {"source": "products", "id": row["id"]},
                        "sku": row["sku"],
                        "brand": row["brand"],
                        "track_inventory": True,
                        "stock_quantity": int(row["qty_on_hand"] or 0),
                    }
                ),
                "image_url": row["image_url"],
                "is_featured": False,
                "requires_site": False,
                "requires_scheduling": False,
                "duration_hours": None,
                "fulfilment_type": "PHYSICAL_SHIPMENT",
                "installed_product_type": row["category_slug"],
                "legacy_source": "products",
                "legacy_source_id": row["id"],
                "published_at": updated_at if active else None,
                "created_at": created_at,
                "updated_at": updated_at,
            },
        )


def upgrade() -> None:
    op.create_table(
        "procurement_suppliers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("legal_name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("contact_email", sa.String(length=320), nullable=True),
        sa.Column("contact_phone", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'ON_HOLD', 'INACTIVE')",
            name="ck_procurement_supplier_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(
        "ix_procurement_suppliers_code", "procurement_suppliers", ["code"], unique=True
    )

    op.create_table(
        "catalog_items",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("item_type", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("sectors_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("asset_types_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("customer_content_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("deliverables_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("price_model", sa.String(length=30), nullable=False, server_default="FIXED"),
        sa.Column("currency", sa.String(length=5), nullable=False, server_default="AOA"),
        sa.Column("unit_amount", sa.Integer(), nullable=True),
        sa.Column("pricing_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("availability_status", sa.String(length=30), nullable=False, server_default="AVAILABLE"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("recommendation_triggers_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("requires_site", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("requires_scheduling", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("duration_hours", sa.Integer(), nullable=True),
        sa.Column("fulfilment_type", sa.String(length=40), nullable=True),
        sa.Column("installed_product_type", sa.String(length=80), nullable=True),
        sa.Column("supplier_id", sa.String(length=36), nullable=True),
        sa.Column("legacy_source", sa.String(length=40), nullable=True),
        sa.Column("legacy_source_id", sa.String(length=100), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "item_type IN ('PHYSICAL_PRODUCT', 'SERVICE', 'MONITORING_PLAN', "
            "'INSTALLATION', 'INSPECTION', 'ANALYSIS')",
            name="ck_catalog_item_type",
        ),
        sa.CheckConstraint(
            "price_model IN ('FIXED', 'STARTING_AT', 'QUOTE', 'SUBSCRIPTION', 'USAGE')",
            name="ck_catalog_price_model",
        ),
        sa.CheckConstraint(
            "availability_status IN ('AVAILABLE', 'UNAVAILABLE', 'PREORDER', 'ON_REQUEST')",
            name="ck_catalog_availability_status",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'UNAVAILABLE', 'ARCHIVED')",
            name="ck_catalog_item_status",
        ),
        sa.CheckConstraint(
            "unit_amount IS NULL OR unit_amount >= 0",
            name="ck_catalog_unit_amount_nonnegative",
        ),
        sa.CheckConstraint(
            "duration_hours IS NULL OR duration_hours > 0",
            name="ck_catalog_duration_positive",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["supplier_id"], ["procurement_suppliers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("legacy_source", "legacy_source_id", name="uq_catalog_items_legacy_source_id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_catalog_items_code", "catalog_items", ["code"], unique=True)
    op.create_index("ix_catalog_items_item_type", "catalog_items", ["item_type"], unique=False)
    op.create_index("ix_catalog_items_slug", "catalog_items", ["slug"], unique=True)
    op.create_index("ix_catalog_items_status", "catalog_items", ["status"], unique=False)
    op.create_index("ix_catalog_items_supplier_id", "catalog_items", ["supplier_id"], unique=False)

    _backfill_shop_products()
    _backfill_basic_products()


def downgrade() -> None:
    op.drop_index("ix_catalog_items_supplier_id", table_name="catalog_items")
    op.drop_index("ix_catalog_items_status", table_name="catalog_items")
    op.drop_index("ix_catalog_items_slug", table_name="catalog_items")
    op.drop_index("ix_catalog_items_item_type", table_name="catalog_items")
    op.drop_index("ix_catalog_items_code", table_name="catalog_items")
    op.drop_table("catalog_items")
    op.drop_index("ix_procurement_suppliers_code", table_name="procurement_suppliers")
    op.drop_table("procurement_suppliers")
