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


def test_operations_resource_migration_preserves_suppliers_and_round_trips(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "operations-resources.sqlite3"
    _alembic(
        backend_dir,
        database_path,
        "upgrade",
        "commercial_order_lifecycle_v1",
    )

    supplier_id = "90000000-0000-4000-8000-000000000001"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO procurement_suppliers
                (id, code, legal_name, status, contact_email, contact_phone,
                 notes, metadata_json, created_at, updated_at)
            VALUES (?, 'PHASE9_SOURCE', 'Existing qualified source', 'ACTIVE',
                    'private@example.com', NULL, 'retain me', '{}',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (supplier_id,),
        )

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        tables = _tables(connection)
        assert {
            "operational_capabilities",
            "operations_contractors",
            "contractor_capabilities",
            "contractor_assignments",
        }.issubset(tables)
        assert {
            "country_code",
            "region",
            "service_area_json",
            "capabilities_json",
            "certifications_json",
            "insurance_json",
            "document_refs_json",
            "quality_score",
        }.issubset(_columns(connection, "procurement_suppliers"))
        assert connection.execute(
            """
            SELECT legal_name, notes, service_area_json, capabilities_json
            FROM procurement_suppliers WHERE id = ?
            """,
            (supplier_id,),
        ).fetchone() == ("Existing qualified source", "retain me", "[]", "[]")
        codes = {
            row[0]
            for row in connection.execute(
                "SELECT code FROM operational_capabilities"
            )
        }
        assert {
            "RGB",
            "RTK",
            "MULTISPECTRAL",
            "THERMAL",
            "LIDAR",
            "AGRICULTURE",
            "INFRASTRUCTURE",
            "ENVIRONMENTAL",
            "MINING",
            "PORTS_INDUSTRIAL",
            "IOT_INSTALLATION",
        }.issubset(codes)

    _alembic(
        backend_dir,
        database_path,
        "downgrade",
        "commercial_order_lifecycle_v1",
    )
    with sqlite3.connect(database_path) as connection:
        assert "operations_contractors" not in _tables(connection)
        assert "operational_capabilities" not in _tables(connection)
        assert "country_code" not in _columns(connection, "procurement_suppliers")
        assert connection.execute(
            "SELECT legal_name, notes FROM procurement_suppliers WHERE id = ?",
            (supplier_id,),
        ).fetchone() == ("Existing qualified source", "retain me")

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT legal_name FROM procurement_suppliers WHERE id = ?",
            (supplier_id,),
        ).fetchone() == ("Existing qualified source",)
        assert connection.execute(
            "SELECT count(*) FROM operational_capabilities"
        ).fetchone() == (15,)
