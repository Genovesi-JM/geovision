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


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }


def test_durable_event_migration_backfills_and_round_trips(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "durable-events.sqlite3"
    _alembic(backend_dir, database_path, "upgrade", "datasets_storage_v2")
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO operational_domain_events
                (id, aggregate_type, aggregate_id, event_type, payload_json,
                 idempotency_key, publish_attempts, occurred_at, published_at)
            VALUES ('10000000-0000-4000-8000-000000000001', 'fulfilment_job',
                    'legacy-job', 'fulfilment_job.created', '{}',
                    'legacy-published-event', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert {"event_consumer_receipts", "event_delivery_attempts"}.issubset(
            _tables(connection)
        )
        assert {
            "topic",
            "schema_version",
            "correlation_id",
            "status",
            "next_attempt_at",
            "claimed_by",
            "dead_lettered_at",
        }.issubset(_columns(connection, "operational_domain_events"))
        assert connection.execute(
            """
            SELECT status, correlation_id, topic
            FROM operational_domain_events
            WHERE id = '10000000-0000-4000-8000-000000000001'
            """
        ).fetchone() == (
            "published",
            "10000000-0000-4000-8000-000000000001",
            "geovision.domain.v1",
        )

    _alembic(backend_dir, database_path, "downgrade", "datasets_storage_v2")
    with sqlite3.connect(database_path) as connection:
        assert "event_consumer_receipts" not in _tables(connection)
        assert "status" not in _columns(connection, "operational_domain_events")
        assert connection.execute(
            "SELECT id FROM operational_domain_events WHERE id = ?",
            ("10000000-0000-4000-8000-000000000001",),
        ).fetchone() is not None

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT status FROM operational_domain_events WHERE id = ?",
            ("10000000-0000-4000-8000-000000000001",),
        ).fetchone() == ("published",)
