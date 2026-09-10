from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def _alembic(backend_dir: Path, database_path: Path, command: str, revision: str) -> None:
    env = os.environ.copy()
    env["ENV"] = "test"
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


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def _indexes(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA index_list({table})")}


def test_odoo_erp_migration_round_trip_preserves_existing_commands(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "phase-21.sqlite3"
    _alembic(backend_dir, database_path, "upgrade", "notification_delivery_v1")
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO integration_outbox (
                id, company_id, provider, aggregate_type, aggregate_id,
                event_type, payload_json, idempotency_key, status, attempts,
                created_at
            ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                "legacy-command",
                "erpnext",
                "order",
                "gv-order-existing",
                "order.created",
                "{}",
                "legacy-order-created-v1",
                "pending",
                0,
            ),
        )
        connection.commit()
        assert "erp_external_references" not in _tables(connection)

    _alembic(backend_dir, database_path, "upgrade", "odoo_erp_v1")
    with sqlite3.connect(database_path) as connection:
        assert {
            "erp_external_references",
            "erp_callback_receipts",
        }.issubset(_tables(connection))
        assert {
            "max_attempts",
            "external_model",
            "last_error_code",
            "claimed_by",
            "claimed_at",
            "lease_expires_at",
            "dead_lettered_at",
            "updated_at",
        }.issubset(_columns(connection, "integration_outbox"))
        assert {
            "invoice_status",
            "stock_status",
            "purchase_status",
            "provider_updated_at",
            "last_callback_at",
        }.issubset(_columns(connection, "erp_external_references"))
        assert {
            "ix_integration_outbox_claimed_by",
            "ix_integration_outbox_lease_expires_at",
        }.issubset(_indexes(connection, "integration_outbox"))
        row = connection.execute(
            "SELECT provider, aggregate_id, max_attempts, updated_at "
            "FROM integration_outbox WHERE id = 'legacy-command'"
        ).fetchone()
        assert row is not None
        assert row[:3] == ("erpnext", "gv-order-existing", 3)
        assert row[3] is not None

    _alembic(backend_dir, database_path, "downgrade", "notification_delivery_v1")
    with sqlite3.connect(database_path) as connection:
        assert "erp_external_references" not in _tables(connection)
        assert "erp_callback_receipts" not in _tables(connection)
        assert "max_attempts" not in _columns(connection, "integration_outbox")
        row = connection.execute(
            "SELECT provider, aggregate_id FROM integration_outbox "
            "WHERE id = 'legacy-command'"
        ).fetchone()
        assert row == ("erpnext", "gv-order-existing")

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert "erp_external_references" in _tables(connection)
