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
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def test_satellite_weather_migration_round_trip(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "satellite-weather.sqlite3"
    expected = {
        "intelligence_schedules",
        "intelligence_acquisitions",
        "satellite_scenes",
        "weather_observations",
    }

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert expected.issubset(_tables(connection))
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(satellite_scenes)")
        }
        assert {
            "provider_reference",
            "acquired_at",
            "cloud_cover_percent",
            "resolution_meters",
            "bands_json",
            "provenance_json",
            "dataset_id",
        }.issubset(columns)

    _alembic(backend_dir, database_path, "downgrade", "processing_jobs_v1")
    with sqlite3.connect(database_path) as connection:
        assert not expected.intersection(_tables(connection))
        assert "processing_jobs" in _tables(connection)

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert expected.issubset(_tables(connection))
