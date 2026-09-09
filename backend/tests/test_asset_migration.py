from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def _alembic(
    backend_dir: Path,
    database_path: Path,
    command: str,
    revision: str,
) -> None:
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
    return {row[1] for row in connection.execute(f"PRAGMA table_info('{table}')")}


def test_asset_migration_backfills_sites_iot_hierarchy_and_portable_geometry(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "asset-migration.sqlite3"
    _alembic(backend_dir, database_path, "upgrade", "organization_rbac_v1")

    organization_id = "50000000-0000-4000-8000-000000000001"
    workspace_id = "50000000-0000-4000-8000-000000000002"
    site_id = "50000000-0000-4000-8000-000000000003"
    iot_asset_id = "50000000-0000-4000-8000-000000000004"

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO companies
                (id, name, email, country, organization_type, timezone,
                 sectors, status, subscription_plan, max_users, max_sites,
                 max_storage_gb, current_users, current_sites, storage_used_gb,
                 created_at, updated_at)
            VALUES (?, 'Existing customer', 'asset-migration@example.test',
                    'Angola', 'customer', 'Africa/Luanda', '[]', 'active',
                    'trial', 5, 10, 50, 0, 1, 0, CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP)
            """,
            (organization_id,),
        )
        connection.execute(
            """
            INSERT INTO accounts
                (id, organization_id, name, sector_focus, entity_type,
                 customer_type, dashboard_profile, use_cases, modules_enabled,
                 status, onboarding_user_id, created_at, updated_at)
            VALUES (?, ?, 'Existing workspace', 'environment', 'company',
                    'business', 'business', '[]', '[]', 'active', NULL,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (workspace_id, organization_id),
        )
        connection.execute(
            """
            INSERT INTO sites
                (id, company_id, name, description, country, province,
                 municipality, latitude, longitude, area_hectares, sector,
                 is_active, created_at, updated_at)
            VALUES (?, ?, 'Wetland A', 'Existing environmental site', 'Angola',
                    'Huambo', 'Caála', -12.852, 15.561, 42.5, 'environment', 1,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (site_id, organization_id),
        )
        connection.execute(
            """
            INSERT INTO iot_assets
                (id, company_id, site_id, name, asset_type,
                 external_reference, latitude, longitude, metadata_json,
                 created_at)
            VALUES (?, ?, ?, 'Tank A', 'tank', 'ERP-42', -12.853, 15.562,
                    '{"capacity_litres":5000}', CURRENT_TIMESTAMP)
            """,
            (iot_asset_id, organization_id, site_id),
        )

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert "assets" in _tables(connection)
        columns = _columns(connection, "assets")
        assert {
            "organization_id",
            "workspace_id",
            "parent_asset_id",
            "sector",
            "asset_type",
            "geometry_geojson",
            "bbox_min_x",
            "bbox_max_y",
            "legacy_source",
            "legacy_source_id",
            "archived_at",
        }.issubset(columns)
        # SQLite is the intentional fallback: PostGIS' generated geometry
        # column is only added on PostgreSQL when the extension is available.
        assert "geometry" not in columns
        site_asset = connection.execute(
            """
            SELECT id, organization_id, workspace_id, sector, asset_type,
                   geometry_geojson, bbox_min_x, bbox_min_y, bbox_max_x,
                   bbox_max_y, legacy_source_id
            FROM assets WHERE legacy_source = 'site'
            """
        ).fetchone()
        assert site_asset == (
            site_id,
            organization_id,
            workspace_id,
            "ENVIRONMENTAL",
            "SITE",
            '{"coordinates":[15.561,-12.852],"type":"Point"}',
            15.561,
            -12.852,
            15.561,
            -12.852,
            site_id,
        )
        iot_asset = connection.execute(
            """
            SELECT id, parent_asset_id, organization_id, workspace_id,
                   sector, asset_type, external_reference, metadata_json
            FROM assets WHERE legacy_source = 'iot_asset'
            """
        ).fetchone()
        assert iot_asset[:7] == (
            iot_asset_id,
            site_id,
            organization_id,
            workspace_id,
            "ENVIRONMENTAL",
            "TANK",
            "ERP-42",
        )
        assert '"capacity_litres":5000' in iot_asset[7]
        indexes = {
            row[1] for row in connection.execute("PRAGMA index_list('assets')")
        }
        assert {
            "ix_assets_scope_type_status",
            "ix_assets_scope_parent",
            "ix_assets_bbox",
        }.issubset(indexes)

    _alembic(
        backend_dir,
        database_path,
        "downgrade",
        "organization_rbac_v1",
    )
    with sqlite3.connect(database_path) as connection:
        assert "assets" not in _tables(connection)
        assert connection.execute("SELECT count(*) FROM sites").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM iot_assets").fetchone() == (1,)

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT count(*) FROM assets").fetchone() == (2,)


def test_postgis_projection_is_conditional_generated_and_gist_indexed():
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "generic_assets_postgis_v1.py"
    ).read_text(encoding="utf-8")
    assert "CREATE EXTENSION postgis" in migration
    assert "GENERATED ALWAYS AS" in migration
    assert "ST_GeomFromGeoJSON" in migration
    assert "geometry(Geometry, 4326)" in migration
    assert "USING GIST (geometry)" in migration
    assert "dialect.name != \"postgresql\"" in migration
