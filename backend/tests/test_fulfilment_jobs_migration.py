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


def _foreign_keys(connection: sqlite3.Connection, table: str) -> set[tuple[str, str, str]]:
    return {
        (row[3], row[2], row[4])
        for row in connection.execute(f"PRAGMA foreign_key_list({table})")
    }


def test_fulfilment_job_migration_round_trip(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "fulfilment-jobs.sqlite3"
    _alembic(backend_dir, database_path, "upgrade", "operations_resources_v1")

    order_id = "a0000000-0000-4000-8000-000000000001"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO orders
                (id, status, currency, subtotal, shipping_fee, discount_total,
                 total, order_number, tax_amount, metadata_json,
                 fulfilment_status, payment_status, order_type,
                 lifecycle_version, created_at, updated_at)
            VALUES (?, 'paid', 'AOA', 100, 0, 0, 100, 'GV-MIGRATION-JOBS',
                    0, '{}', 'PAID', 'PAID', 'SERVICE', 1,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (order_id,),
        )

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert {
            "fulfilment_jobs",
            "fulfilment_job_dependencies",
            "operational_domain_events",
        }.issubset(_tables(connection))
        assert (
            "fulfilment_job_id",
            "fulfilment_jobs",
            "id",
        ) in _foreign_keys(connection, "contractor_assignments")
        connection.execute(
            """
            INSERT INTO fulfilment_jobs
                (id, job_number, order_id, job_type, title, priority, state,
                 requirements_json, lifecycle_version, created_at, updated_at)
            VALUES ('job-migration', 'GVJ-MIGRATION', ?, 'PROCESS_DATA',
                    'Migration processing job', 'NORMAL', 'PLANNED', '{}', 1,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (order_id,),
        )
        connection.execute(
            """
            INSERT INTO operational_domain_events
                (id, aggregate_type, aggregate_id, event_type, payload_json,
                 idempotency_key, publish_attempts, occurred_at)
            VALUES ('event-migration', 'fulfilment_job', 'job-migration',
                    'fulfilment_job.created', '{}', 'migration-event', 0,
                    CURRENT_TIMESTAMP)
            """
        )

    _alembic(backend_dir, database_path, "downgrade", "operations_resources_v1")
    with sqlite3.connect(database_path) as connection:
        assert "fulfilment_jobs" not in _tables(connection)
        assert "operational_domain_events" not in _tables(connection)
        assert not any(
            foreign_table == "fulfilment_jobs"
            for _, foreign_table, _ in _foreign_keys(connection, "contractor_assignments")
        )
        assert connection.execute(
            "SELECT order_number FROM orders WHERE id = ?", (order_id,)
        ).fetchone() == ("GV-MIGRATION-JOBS",)

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert "fulfilment_jobs" in _tables(connection)
        assert (
            "fulfilment_job_id",
            "fulfilment_jobs",
            "id",
        ) in _foreign_keys(connection, "contractor_assignments")
        assert connection.execute(
            "SELECT order_number FROM orders WHERE id = ?", (order_id,)
        ).fetchone() == ("GV-MIGRATION-JOBS",)
