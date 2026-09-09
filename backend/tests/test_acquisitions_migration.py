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


def test_acquisition_migration_maps_legacy_records_and_round_trips(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "acquisitions.sqlite3"
    _alembic(backend_dir, database_path, "upgrade", "fulfilment_jobs_v1")

    user_id = "b0000000-0000-4000-8000-000000000001"
    organization_id = "b0000000-0000-4000-8000-000000000002"
    workspace_id = "b0000000-0000-4000-8000-000000000003"
    site_id = "b0000000-0000-4000-8000-000000000004"
    generic_site_id = "b0000000-0000-4000-8000-000000000005"
    legacy_asset_id = "b0000000-0000-4000-8000-000000000006"
    generic_asset_id = "b0000000-0000-4000-8000-000000000007"
    aircraft_id = "b0000000-0000-4000-8000-000000000008"
    mission_id = "b0000000-0000-4000-8000-000000000009"
    inspection_id = "b0000000-0000-4000-8000-000000000010"

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO users
                (id, email, role, is_active, auth_generation, created_at, updated_at)
            VALUES (?, 'migration-pilot@example.com', 'client', 1, 0,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (user_id,),
        )
        connection.execute(
            """
            INSERT INTO companies
                (id, name, email, country, organization_type, timezone,
                 sectors, status, subscription_plan, max_users, max_sites,
                 max_storage_gb, current_users, current_sites, storage_used_gb,
                 created_at, updated_at)
            VALUES (?, 'Mission migration customer', 'migration@example.com',
                    'Angola', 'customer', 'Africa/Luanda', '[]', 'active',
                    'trial', 5, 10, 50, 1, 1, 0,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (organization_id,),
        )
        connection.execute(
            """
            INSERT INTO accounts
                (id, organization_id, name, sector_focus, entity_type,
                 customer_type, dashboard_profile, use_cases, modules_enabled,
                 status, created_at, updated_at)
            VALUES (?, ?, 'Mission workspace', 'environment', 'company',
                    'business', 'business', '[]', '[]', 'active',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (workspace_id, organization_id),
        )
        connection.execute(
            """
            INSERT INTO sites
                (id, company_id, name, country, province, municipality,
                 latitude, longitude, sector, is_active, created_at, updated_at)
            VALUES (?, ?, 'Mapped site', 'Angola', 'Luanda', 'Belas',
                    -8.9, 13.2, 'environment', 1,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (site_id, organization_id),
        )
        connection.execute(
            """
            INSERT INTO iot_assets
                (id, company_id, site_id, name, asset_type, latitude,
                 longitude, metadata_json, created_at)
            VALUES (?, ?, ?, 'Bridge pier', 'structure', -8.91, 13.21, '{}',
                    CURRENT_TIMESTAMP)
            """,
            (legacy_asset_id, organization_id, site_id),
        )
        for values in (
            (generic_site_id, None, "SITE", "Mapped site", "site", site_id),
            (
                generic_asset_id,
                generic_site_id,
                "STRUCTURE",
                "Bridge pier",
                "iot_asset",
                legacy_asset_id,
            ),
        ):
            connection.execute(
                """
                INSERT INTO assets
                    (id, organization_id, workspace_id, parent_asset_id,
                     sector, asset_type, name, status, metadata_json,
                     legacy_source, legacy_source_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'ENVIRONMENTAL', ?, ?, 'active', '{}',
                        ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    values[0],
                    organization_id,
                    workspace_id,
                    values[1],
                    values[2],
                    values[3],
                    values[4],
                    values[5],
                ),
            )
        connection.execute(
            """
            INSERT INTO drone_aircraft
                (id, company_id, site_id, name, manufacturer, model, provider,
                 connection_mode, sdk_supported, status, capabilities_json,
                 created_at, updated_at)
            VALUES (?, ?, ?, 'Survey aircraft', 'DJI', 'Mavic 3M',
                    'dji_mobile_sdk', 'sdk_handoff', 1, 'registered', '[]',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (aircraft_id, organization_id, site_id),
        )
        connection.execute(
            """
            INSERT INTO drone_missions
                (id, company_id, site_id, aircraft_id, created_by, name,
                 mission_type, status, altitude_m, speed_mps,
                 front_overlap_percent, side_overlap_percent, boundary_json,
                 route_json, checklist_json, provider_reference,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'Legacy wetland flight', 'multispectral',
                    'completed', 80, 5, 80, 70,
                    '[{"lat":-8.9,"lng":13.2},{"lat":-8.9,"lng":13.3},{"lat":-8.8,"lng":13.2}]',
                    '[]', '{"airspace_checked":true}', 'DJI-LEGACY-42',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (mission_id, organization_id, site_id, aircraft_id, user_id),
        )
        connection.execute(
            """
            INSERT INTO asset_inspections
                (id, company_id, asset_id, site_id, inspected_by,
                 inspector_name, category, result, notes, checklist_json,
                 photos_json, latitude, longitude, created_at)
            VALUES (?, ?, ?, ?, ?, 'migration pilot', 'structural',
                    'attention', 'Crack requires review',
                    '{"surface_checked":true}', '["photo-1"]', -8.91, 13.21,
                    CURRENT_TIMESTAMP)
            """,
            (inspection_id, organization_id, legacy_asset_id, site_id, user_id),
        )

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert {"acquisitions", "drone_acquisition_details"}.issubset(
            _tables(connection)
        )
        rows = connection.execute(
            """
            SELECT acquisition_type, asset_id, state, legacy_source,
                   legacy_source_id, provider_code
            FROM acquisitions ORDER BY acquisition_type
            """
        ).fetchall()
        assert rows == [
            (
                "DRONE",
                generic_site_id,
                "COMPLETED",
                "drone_mission",
                mission_id,
                "dji_mobile_sdk",
            ),
            (
                "MANUAL_INSPECTION",
                generic_asset_id,
                "COMPLETED",
                "asset_inspection",
                inspection_id,
                "geovision_manual",
            ),
        ]
        detail = connection.execute(
            """
            SELECT aircraft_id, capture_area_geojson, mission_requirements_json
            FROM drone_acquisition_details
            """
        ).fetchone()
        assert detail[0] == aircraft_id
        assert '"type":"Polygon"' in detail[1]
        assert '"altitude_m":80' in detail[2]

    _alembic(backend_dir, database_path, "downgrade", "fulfilment_jobs_v1")
    with sqlite3.connect(database_path) as connection:
        assert "acquisitions" not in _tables(connection)
        assert connection.execute(
            "SELECT name, status FROM drone_missions WHERE id = ?", (mission_id,)
        ).fetchone() == ("Legacy wetland flight", "completed")
        assert connection.execute(
            "SELECT result, notes FROM asset_inspections WHERE id = ?", (inspection_id,)
        ).fetchone() == ("attention", "Crack requires review")

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT count(*) FROM acquisitions").fetchone() == (2,)
        assert connection.execute(
            "SELECT count(*) FROM drone_acquisition_details"
        ).fetchone() == (1,)
