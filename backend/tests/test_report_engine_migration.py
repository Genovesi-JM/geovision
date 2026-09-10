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


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def test_report_engine_migration_round_trip(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "phase-19.sqlite3"
    _alembic(backend_dir, database_path, "upgrade", "kpi_observation_action_v1")
    with sqlite3.connect(database_path) as connection:
        assert "reports" not in _tables(connection)

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert "reports" in _tables(connection)
        assert {
            "organization_id",
            "workspace_id",
            "asset_id",
            "acquisition_id",
            "report_type",
            "revision",
            "status",
            "qa_level",
            "context_json",
            "context_sha256",
            "narrative_json",
            "qa_result_json",
            "output_dataset_id",
            "output_file_id",
            "supersedes_report_id",
            "generation_key",
            "approved_at",
            "published_at",
            "lifecycle_version",
        }.issubset(_columns(connection, "reports"))

    _alembic(backend_dir, database_path, "downgrade", "kpi_observation_action_v1")
    with sqlite3.connect(database_path) as connection:
        assert "reports" not in _tables(connection)

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert "reports" in _tables(connection)
