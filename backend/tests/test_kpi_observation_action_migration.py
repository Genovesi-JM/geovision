from __future__ import annotations

from datetime import datetime
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
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def test_kpi_observation_action_migration_backfills_and_round_trips(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "phase-17.sqlite3"
    _alembic(backend_dir, database_path, "upgrade", "iot_edge_contract_v1")
    now = datetime(2026, 9, 10, 8).isoformat()

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO companies
                (id, name, email, country, sectors, status, subscription_plan,
                 max_users, max_sites, max_storage_gb, current_users,
                 current_sites, storage_used_gb, created_at, updated_at)
            VALUES
                ('company-17', 'Phase 17', 'phase17@example.test', 'Angola',
                 '[]', 'active', 'starter', 5, 5, 5, 0, 0, 0, ?, ?)
            """,
            (now, now),
        )
        connection.execute(
            """
            INSERT INTO accounts
                (id, organization_id, name, sector_focus, entity_type,
                 customer_type, dashboard_profile, use_cases, modules_enabled,
                 status, created_at, updated_at)
            VALUES
                ('workspace-17', 'company-17', 'Phase 17 workspace', 'agro',
                 'business', 'business', 'farm', '[]', '["kpi"]', 'active', ?, ?)
            """,
            (now, now),
        )
        connection.execute(
            """
            INSERT INTO sites
                (id, company_id, name, country, sector, is_active, created_at, updated_at)
            VALUES
                ('site-17', 'company-17', 'Legacy field', 'Angola', 'agriculture', 1, ?, ?)
            """,
            (now, now),
        )
        connection.execute(
            """
            INSERT INTO assets
                (id, organization_id, workspace_id, sector, asset_type, name,
                 status, metadata_json, legacy_source, legacy_source_id,
                 created_at, updated_at)
            VALUES
                ('asset-17', 'company-17', 'workspace-17', 'AGRICULTURE',
                 'FIELD', 'Legacy field', 'active', '{}', 'site', 'site-17', ?, ?)
            """,
            (now, now),
        )
        connection.execute(
            """
            INSERT INTO kpi_definitions
                (id, sector, key, label, sort_order, is_active, created_at)
            VALUES
                ('definition-17', 'agro', 'legacy_metric', 'Legacy metric', 0, 1, ?)
            """,
            (now,),
        )
        connection.execute(
            """
            INSERT INTO kpi_values
                (id, kpi_definition_id, account_id, site_id, value,
                 numeric_value, recorded_at, created_at)
            VALUES
                ('value-17', 'definition-17', 'workspace-17', 'site-17',
                 '42', 42, ?, ?)
            """,
            (now, now),
        )
        connection.commit()

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert {"observations", "intelligence_actions"}.issubset(_tables(connection))
        assert {
            "name",
            "calculator",
            "calculator_version",
            "importance",
            "display_format_json",
            "status_policy_json",
        }.issubset(_columns(connection, "kpi_definitions"))
        assert {
            "organization_id",
            "workspace_id",
            "asset_id",
            "status",
            "confidence",
            "measured_at",
            "source",
            "algorithm_version",
            "provenance_json",
            "is_baseline",
        }.issubset(_columns(connection, "kpi_values"))
        definition = connection.execute(
            """
            SELECT name, calculator, calculator_version, importance
              FROM kpi_definitions WHERE id = 'definition-17'
            """
        ).fetchone()
        assert definition == ("Legacy metric", "legacy_metric", "legacy-1", "TECHNICAL")
        value = connection.execute(
            """
            SELECT organization_id, workspace_id, asset_id, measured_at,
                   status, confidence
              FROM kpi_values WHERE id = 'value-17'
            """
        ).fetchone()
        assert value[:3] == ("company-17", "workspace-17", "asset-17")
        assert value[3] == now
        assert value[4:] == ("UNKNOWN", 0.0)

    _alembic(backend_dir, database_path, "downgrade", "iot_edge_contract_v1")
    with sqlite3.connect(database_path) as connection:
        assert "observations" not in _tables(connection)
        assert "intelligence_actions" not in _tables(connection)
        assert "name" not in _columns(connection, "kpi_definitions")
        assert "asset_id" not in _columns(connection, "kpi_values")
        assert connection.execute(
            "SELECT label FROM kpi_definitions WHERE id = 'definition-17'"
        ).fetchone() == ("Legacy metric",)

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert {"observations", "intelligence_actions"}.issubset(_tables(connection))
