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


def test_processing_job_migration_round_trip(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "processing-jobs.sqlite3"
    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert {
            "processing_jobs",
            "processing_job_sources",
            "processing_job_outputs",
        }.issubset(_tables(connection))
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(processing_jobs)")
        }
        assert {
            "provider_job_reference",
            "requested_outputs_json",
            "progress_percent",
            "estimated_cost_amount",
            "actual_cost_amount",
            "quality_report_json",
            "retry_count",
            "next_poll_at",
            "processor_version",
        }.issubset(columns)

    _alembic(backend_dir, database_path, "downgrade", "durable_events_v1")
    with sqlite3.connect(database_path) as connection:
        assert "processing_jobs" not in _tables(connection)
        assert "operational_domain_events" in _tables(connection)

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert "processing_jobs" in _tables(connection)
