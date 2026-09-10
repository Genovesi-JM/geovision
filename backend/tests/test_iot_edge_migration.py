from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone


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


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def test_iot_edge_migration_round_trip(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "iot-edge.sqlite3"

    _alembic(backend_dir, database_path, "upgrade", "satellite_weather_v1")
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO companies
                (id, name, email, country, sectors, status, subscription_plan,
                 max_users, max_sites, max_storage_gb, current_users,
                 current_sites, storage_used_gb, created_at, updated_at)
            VALUES
                ('company-1', 'Migration tenant', 'migration@example.test',
                 'Spain', '[]', 'active', 'starter', 5, 5, 5, 0, 0, 0, ?, ?)
            """,
            (now, now),
        )
        connection.execute(
            """
            INSERT INTO sites
                (id, company_id, name, sector, is_active, created_at, updated_at, country)
            VALUES ('site-1', 'company-1', 'Migration site', 'agriculture', 1, ?, ?, 'Spain')
            """,
            (now, now),
        )
        connection.execute(
            """
            INSERT INTO assets
                (id, organization_id, sector, asset_type, name, status,
                 metadata_json, legacy_source, legacy_source_id, created_at, updated_at)
            VALUES
                ('asset-1', 'company-1', 'AGRICULTURE', 'SITE', 'Migration site',
                 'active', '{}', 'site', 'site-1', ?, ?)
            """,
            (now, now),
        )
        connection.execute(
            """
            INSERT INTO iot_devices
                (id, public_id, company_id, site_id, name, device_type,
                 transport, status, token_hash, secret_encrypted,
                 capabilities_json, configuration_json, allow_remote_control,
                 created_at, updated_at)
            VALUES
                ('device-1', 'gv-migration', 'company-1', 'site-1',
                 'Migration sensor', 'multi_sensor', 'rest', 'online',
                 'hash', 'plain:test', '[]', '{}', 0, ?, ?)
            """,
            (now, now),
        )
        connection.commit()

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert {
            "iot_device_assignments",
            "iot_telemetry_receipts",
        }.issubset(_tables(connection))
        assert {
            "core_asset_id",
            "provider_code",
            "provider_device_id",
            "protocol_version",
            "connectivity_status",
            "battery_percent",
            "health_status",
            "last_stream_id",
            "last_sequence",
        }.issubset(_columns(connection, "iot_devices"))
        assert {
            "receipt_id",
            "core_asset_id",
            "sequence",
            "protocol_version",
            "source",
        }.issubset(_columns(connection, "telemetry_readings"))
        device = connection.execute(
            """
            SELECT core_asset_id, provider_code, provider_device_id,
                   connectivity_status
              FROM iot_devices WHERE id = 'device-1'
            """
        ).fetchone()
        assert device == ("asset-1", "geovision", "gv-migration", "online")
        assignment = connection.execute(
            """
            SELECT device_id, asset_id, status
              FROM iot_device_assignments WHERE device_id = 'device-1'
            """
        ).fetchone()
        assert assignment == ("device-1", "asset-1", "active")

    _alembic(backend_dir, database_path, "downgrade", "satellite_weather_v1")
    with sqlite3.connect(database_path) as connection:
        assert "iot_device_assignments" not in _tables(connection)
        assert "iot_telemetry_receipts" not in _tables(connection)
        assert "core_asset_id" not in _columns(connection, "iot_devices")
        assert "receipt_id" not in _columns(connection, "telemetry_readings")
        assert "satellite_scenes" in _tables(connection)

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert "iot_device_assignments" in _tables(connection)
        assert "iot_telemetry_receipts" in _tables(connection)
