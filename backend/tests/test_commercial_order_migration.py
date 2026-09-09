from __future__ import annotations

import json
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


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }


def test_commercial_order_migration_backfills_and_round_trips(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "commercial-order-migration.sqlite3"
    _alembic(backend_dir, database_path, "upgrade", "invitation_onboarding_v1")

    product_id = "prod_phase8_migration"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO shop_products
                (id, name, slug, product_type, category, price, price_usd,
                 price_eur, currency, tax_rate, requires_site, sectors_json,
                 deliverables_json, is_active, is_featured, track_inventory,
                 stock_quantity, created_at, updated_at)
            VALUES (?, 'Migration service', 'migration-service', 'service',
                    'inspection', 125000, 1500, 1400, 'AOA', 0.14, 1,
                    '["agro"]', '["Report"]', 1, 0, 0, 0,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (product_id,),
        )
    _alembic(backend_dir, database_path, "upgrade", "first_party_catalog_v1")

    order_id = "80000000-0000-4000-8000-000000000001"
    item_id = "80000000-0000-4000-8000-000000000002"
    payment_id = "80000000-0000-4000-8000-000000000003"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO orders
                (id, status, currency, subtotal, shipping_fee, discount_total,
                 total, order_number, tax_amount, metadata_json, created_at,
                 updated_at)
            VALUES (?, 'processing', 'AOA', 125000, 0, 0, 125000,
                    'GV-2026-MIGRATION', 15351, '{}', CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP)
            """,
            (order_id,),
        )
        connection.execute(
            """
            INSERT INTO order_items
                (id, order_id, product_id, sku, name, unit_price, qty, line_total)
            VALUES (?, ?, ?, 'MIGRATION-SERVICE', 'Migration service',
                    125000, 1, 125000)
            """,
            (item_id, order_id, product_id),
        )
        connection.execute(
            """
            INSERT INTO payments
                (id, company_id, order_id, amount, currency, provider, status,
                 provider_reference, metadata_json, created_at, updated_at)
            VALUES (?, 'legacy-company', ?, 125000, 'AOA', 'iban_transfer',
                    'completed', 'GV-MIGRATION', '{}', CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP)
            """,
            (payment_id, order_id),
        )

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert "payment_webhook_events" in _tables(connection)
        assert "legacy_payment_webhook_events" in _tables(connection)
        assert "payload_sha256" in _columns(connection, "payment_webhook_events")
        assert "payload" in _columns(connection, "legacy_payment_webhook_events")
        assert {
            "organization_id",
            "workspace_id",
            "order_type",
            "fulfilment_status",
            "payment_status",
            "checkout_idempotency_key",
        }.issubset(_columns(connection, "orders"))
        order = connection.execute(
            """
            SELECT order_type, fulfilment_status, payment_status
            FROM orders WHERE id = ?
            """,
            (order_id,),
        ).fetchone()
        assert order == ("SERVICE", "PROCESSING", "PAID")
        item = connection.execute(
            """
            SELECT catalog_item_id, catalog_item_type, currency,
                   pricing_snapshot_json
            FROM order_items WHERE id = ?
            """,
            (item_id,),
        ).fetchone()
        assert item[:3] == (product_id, "INSPECTION", "AOA")
        snapshot = json.loads(item[3])
        assert snapshot["catalog_item_id"] == product_id
        assert snapshot["unit_amount"] == 125000
        payment = connection.execute(
            """
            SELECT organization_id, refunded_amount, completed_at
            FROM payments WHERE id = ?
            """,
            (payment_id,),
        ).fetchone()
        assert payment[0] is None
        assert payment[1] == 0
        assert payment[2] is not None

    _alembic(backend_dir, database_path, "downgrade", "first_party_catalog_v1")
    with sqlite3.connect(database_path) as connection:
        assert "payment_webhook_events" in _tables(connection)
        assert "legacy_payment_webhook_events" not in _tables(connection)
        assert "payload" in _columns(connection, "payment_webhook_events")
        assert "fulfilment_status" not in _columns(connection, "orders")
        assert "catalog_item_id" not in _columns(connection, "order_items")
        assert connection.execute(
            "SELECT status, total FROM orders WHERE id = ?", (order_id,)
        ).fetchone() == ("processing", 125000)
        assert connection.execute(
            "SELECT status FROM payments WHERE id = ?", (payment_id,)
        ).fetchone() == ("completed",)

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT fulfilment_status, payment_status FROM orders WHERE id = ?",
            (order_id,),
        ).fetchone() == ("PROCESSING", "PAID")
