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


def test_dataset_migration_backfills_legacy_metadata_and_round_trips(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "datasets.sqlite3"
    _alembic(backend_dir, database_path, "upgrade", "acquisitions_v1")

    user_id = "c0000000-0000-4000-8000-000000000001"
    organization_id = "c0000000-0000-4000-8000-000000000002"
    workspace_id = "c0000000-0000-4000-8000-000000000003"
    site_id = "c0000000-0000-4000-8000-000000000004"
    asset_id = "c0000000-0000-4000-8000-000000000005"
    dataset_id = "c0000000-0000-4000-8000-000000000006"
    file_id = "c0000000-0000-4000-8000-000000000007"

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO users
                (id, email, role, is_active, auth_generation, created_at, updated_at)
            VALUES (?, 'dataset-migration@example.com', 'client', 1, 0,
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
            VALUES (?, 'Dataset migration', 'dataset@example.com', 'Angola',
                    'customer', 'Africa/Luanda', '[]', 'active', 'trial',
                    5, 10, 50, 1, 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (organization_id,),
        )
        connection.execute(
            """
            INSERT INTO accounts
                (id, organization_id, name, sector_focus, entity_type,
                 customer_type, dashboard_profile, use_cases, modules_enabled,
                 status, created_at, updated_at)
            VALUES (?, ?, 'Dataset workspace', 'environment', 'company',
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
            VALUES (?, ?, 'Dataset site', 'Angola', 'Luanda', 'Belas',
                    -8.9, 13.2, 'environment', 1,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (site_id, organization_id),
        )
        connection.execute(
            """
            INSERT INTO assets
                (id, organization_id, workspace_id, sector, asset_type, name,
                 status, metadata_json, legacy_source, legacy_source_id,
                 created_at, updated_at)
            VALUES (?, ?, ?, 'ENVIRONMENTAL', 'SITE', 'Dataset site', 'active',
                    '{}', 'site', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (asset_id, organization_id, workspace_id, site_id),
        )
        connection.execute(
            """
            INSERT INTO datasets
                (id, site_id, name, description, data_type, source,
                 connector_id, collection_date, processing_date, storage_path,
                 storage_size_mb, file_count, status, extra_data,
                 created_at, updated_at)
            VALUES (?, ?, 'Legacy orthomosaic', 'Mapped safely', 'orthomosaic',
                    'pix4d', NULL, '2026-08-01 10:00:00',
                    '2026-08-01 12:00:00',
                    'companies/legacy/datasets/orthomosaic', 1.5, 1,
                    'complete', '{"gsd_cm":4.2}',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (dataset_id, site_id),
        )
        connection.execute(
            """
            INSERT INTO dataset_files
                (id, dataset_id, filename, storage_key, file_size, mime_type,
                 status, created_at)
            VALUES (?, ?, 'ortho.tif',
                    'companies/legacy/datasets/orthomosaic/ortho.tif',
                    1572864, 'image/tiff', 'pending', CURRENT_TIMESTAMP)
            """,
            (file_id, dataset_id),
        )

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        dataset = connection.execute(
            """
            SELECT company_id, workspace_id, asset_id, dataset_type,
                   provider_code, source_reference, storage_provider,
                   processing_level, quality_status, capture_date,
                   processed_at, total_size_bytes, metadata_json, status
            FROM datasets WHERE id = ?
            """,
            (dataset_id,),
        ).fetchone()
        assert dataset == (
            organization_id,
            workspace_id,
            asset_id,
            "ORTHOMOSAIC",
            "pix4d",
            "pix4d",
            "s3",
            "RAW",
            "UNREVIEWED",
            "2026-08-01 10:00:00",
            "2026-08-01 12:00:00",
            1572864,
            '{"gsd_cm":4.2}',
            "ready",
        )
        file = connection.execute(
            """
            SELECT storage_provider, storage_uri, object_area, file_size,
                   status, confirmed_at, lifecycle_version
            FROM dataset_files WHERE id = ?
            """,
            (file_id,),
        ).fetchone()
        assert file[0:5] == (
            "s3",
            "s3://companies/legacy/datasets/orthomosaic/ortho.tif",
            "raw",
            1572864,
            "uploaded",
        )
        assert file[5] is not None and file[6] == 1
        dataset_foreign_keys = {
            row[3]: row[6]
            for row in connection.execute("PRAGMA foreign_key_list(datasets)")
        }
        assert dataset_foreign_keys["company_id"] == "RESTRICT"
        assert dataset_foreign_keys["site_id"] == "SET NULL"
        file_foreign_keys = {
            row[3]: row[6]
            for row in connection.execute("PRAGMA foreign_key_list(dataset_files)")
        }
        assert file_foreign_keys["dataset_id"] == "RESTRICT"

    _alembic(backend_dir, database_path, "downgrade", "acquisitions_v1")
    with sqlite3.connect(database_path) as connection:
        assert "dataset_type" not in _columns(connection, "datasets")
        assert "sha256_hash" not in _columns(connection, "dataset_files")
        assert connection.execute(
            "SELECT name, storage_path FROM datasets WHERE id = ?", (dataset_id,)
        ).fetchone() == (
            "Legacy orthomosaic",
            "companies/legacy/datasets/orthomosaic",
        )
        assert connection.execute(
            "SELECT filename, storage_key FROM dataset_files WHERE id = ?", (file_id,)
        ).fetchone() == (
            "ortho.tif",
            "companies/legacy/datasets/orthomosaic/ortho.tif",
        )

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT count(*) FROM datasets").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM dataset_files").fetchone() == (1,)
        assert connection.execute(
            "SELECT dataset_type, asset_id FROM datasets WHERE id = ?", (dataset_id,)
        ).fetchone() == ("ORTHOMOSAIC", asset_id)
        company_foreign_keys = [
            row
            for row in connection.execute("PRAGMA foreign_key_list(datasets)")
            if row[3] == "company_id"
        ]
        assert len(company_foreign_keys) == 1
