from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def _alembic(backend_dir: Path, database_path: Path, command: str, revision: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path}"
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", command, revision],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }


def test_catalog_migration_preserves_and_backfills_both_legacy_stores(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "catalog-migration.sqlite3"
    _alembic(backend_dir, database_path, "upgrade", "invitation_onboarding_v1")

    shop_id = "prod_existing_phase7"
    product_id = "70000000-0000-4000-8000-000000000001"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO shop_products
                (id, name, slug, description, short_description, product_type,
                 category, execution_type, price, price_usd, price_eur,
                 currency, tax_rate, duration_hours, requires_site, min_area_ha,
                 sectors_json, deliverables_json, image_url, is_active,
                 is_featured, track_inventory, stock_quantity, created_at,
                 updated_at)
            VALUES (?, 'Existing inspection', 'existing-inspection',
                    'Existing customer data', 'Inspection', 'service',
                    'inspection', 'pontual', 10000, 100, 90, 'AOA', 0.14,
                    4, 1, 1, '["agro"]', '["Report"]', NULL, 1, 1, 0, 0,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (shop_id,),
        )
        connection.execute(
            """
            INSERT INTO products
                (id, sku, name, description, brand, unit, price, currency,
                 is_active, created_at, updated_at, category_id)
            VALUES (?, 'LEGACY-SENSOR-7', 'Existing sensor', 'Retained stock',
                    'GeoVision', 'unit', 2500, 'AOA', 0,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL)
            """,
            (product_id,),
        )

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert {"catalog_items", "procurement_suppliers"}.issubset(_tables(connection))
        shop = connection.execute(
            """
            SELECT id, item_type, status, sectors_json, legacy_source_id
            FROM catalog_items WHERE legacy_source = 'shop_products'
            """
        ).fetchone()
        assert shop == (
            shop_id,
            "INSPECTION",
            "PUBLISHED",
            '["AGRICULTURE"]',
            shop_id,
        )
        inventory = connection.execute(
            """
            SELECT item_type, status, unit_amount, legacy_source_id
            FROM catalog_items WHERE legacy_source = 'products'
            """
        ).fetchone()
        assert inventory == ("PHYSICAL_PRODUCT", "ARCHIVED", 2500, product_id)

    _alembic(backend_dir, database_path, "downgrade", "invitation_onboarding_v1")
    with sqlite3.connect(database_path) as connection:
        assert "catalog_items" not in _tables(connection)
        assert "procurement_suppliers" not in _tables(connection)
        assert connection.execute(
            "SELECT name FROM shop_products WHERE id = ?", (shop_id,)
        ).fetchone() == ("Existing inspection",)
        assert connection.execute(
            "SELECT name FROM products WHERE id = ?", (product_id,)
        ).fetchone() == ("Existing sensor",)

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT count(*) FROM catalog_items").fetchone() == (2,)
