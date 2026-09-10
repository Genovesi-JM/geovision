from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


def _alembic(
    backend_dir: Path,
    database_path: Path,
    command: str,
    revision: str,
) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path}"
    subprocess.run(
        [sys.executable, "-m", "alembic", command, revision],
        cwd=backend_dir,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info('{table}')")}


def test_service_request_journey_migration_backfills_and_quarantines_orphans(
    tmp_path,
):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "service-request-journey.sqlite3"
    _alembic(backend_dir, database_path, "upgrade", "integration_registry_v1")

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            INSERT INTO users
                (id, email, role, is_active, auth_generation, created_at, updated_at)
            VALUES ('journey-user', 'journey@example.test', 'client', 1, 0,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

            INSERT INTO companies
                (id, name, email, country, organization_type, timezone, sectors,
                 status, subscription_plan, max_users, max_sites, max_storage_gb,
                 current_users, current_sites, storage_used_gb, created_at, updated_at)
            VALUES ('journey-org', 'Journey org', 'journey-org@example.test',
                    'Angola', 'customer', 'Africa/Luanda', '[]', 'active', 'trial',
                    5, 10, 50, 1, 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

            INSERT INTO accounts
                (id, organization_id, name, sector_focus, entity_type,
                 customer_type, dashboard_profile, use_cases, modules_enabled,
                 status, created_at, updated_at)
            VALUES ('journey-workspace', 'journey-org', 'Journey workspace',
                    'agriculture', 'company', 'business', 'business', '[]', '[]',
                    'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

            INSERT INTO companies
                (id, name, email, country, organization_type, timezone, sectors,
                 status, subscription_plan, max_users, max_sites, max_storage_gb,
                 current_users, current_sites, storage_used_gb, created_at, updated_at)
            VALUES ('ambiguous-org', 'Ambiguous org', 'ambiguous@example.test',
                    'Angola', 'customer', 'Africa/Luanda', '[]', 'active', 'trial',
                    5, 10, 50, 1, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

            INSERT INTO accounts
                (id, organization_id, name, sector_focus, entity_type,
                 customer_type, dashboard_profile, use_cases, modules_enabled,
                 status, created_at, updated_at)
            VALUES
                ('ambiguous-workspace-a', 'ambiguous-org', 'Ambiguous A',
                 'agriculture', 'company', 'business', 'business', '[]', '[]',
                 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                ('ambiguous-workspace-b', 'ambiguous-org', 'Ambiguous B',
                 'agriculture', 'company', 'business', 'business', '[]', '[]',
                 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

            INSERT INTO sites
                (id, company_id, name, country, province, municipality, latitude,
                 longitude, sector, is_active, created_at, updated_at)
            VALUES ('journey-site', 'journey-org', 'Journey site', 'Angola',
                    'Huambo', 'Caála', -12.8, 15.5, 'agriculture', 1,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

            INSERT INTO assets
                (id, organization_id, workspace_id, sector, asset_type, name,
                 status, metadata_json, legacy_source, legacy_source_id,
                 created_at, updated_at)
            VALUES ('journey-asset', 'journey-org', 'journey-workspace',
                    'AGRICULTURE', 'SITE', 'Journey site', 'active', '{}', 'site',
                    'journey-site', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

            INSERT INTO mobile_service_requests
                (id, user_id, site_id, site_name, request_type, urgency,
                 description, status, progress_percent, attachments_json,
                 created_at, updated_at)
            VALUES
                ('mapped-request', 'journey-user', 'journey-site', 'Journey site',
                 'inspection', 'normal', 'Mapped history', 'COMPLETED', 150, '[]',
                 CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                ('orphan-request', 'journey-user', NULL, 'Deleted site',
                 'inspection', 'normal', 'Quarantined history', 'legacy_unknown',
                 -5, '[]', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

            INSERT INTO account_events
                (id, company_id, event_type, resource_type, resource_id, title,
                 payload_json, created_at)
            VALUES ('legacy-account-event', 'journey-org', 'legacy.event', 'legacy',
                    NULL, 'Legacy event', '{}', CURRENT_TIMESTAMP);

            INSERT INTO account_events
                (id, company_id, event_type, resource_type, resource_id, title,
                 payload_json, created_at)
            VALUES ('ambiguous-account-event', 'ambiguous-org', 'legacy.event',
                    'legacy', NULL, 'Ambiguous legacy event', '{}',
                    CURRENT_TIMESTAMP);
            """
        )
        connection.commit()

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        assert {
            "organization_id",
            "workspace_id",
            "asset_id",
            "order_id",
            "report_id",
            "idempotency_key",
            "request_sha256",
            "lifecycle_version",
        }.issubset(_columns(connection, "mobile_service_requests"))
        assert "workspace_id" in _columns(connection, "account_events")
        assert connection.execute(
            """
            SELECT organization_id, workspace_id, asset_id, status,
                   progress_percent, lifecycle_version
            FROM mobile_service_requests WHERE id = 'mapped-request'
            """
        ).fetchone() == (
            "journey-org",
            "journey-workspace",
            "journey-asset",
            "completed",
            100,
            1,
        )
        assert connection.execute(
            """
            SELECT organization_id, workspace_id, asset_id, status,
                   progress_percent
            FROM mobile_service_requests WHERE id = 'orphan-request'
            """
        ).fetchone() == (None, None, None, "submitted", 0)
        assert connection.execute(
            "SELECT workspace_id FROM account_events WHERE id = 'legacy-account-event'"
        ).fetchone() == ("journey-workspace",)
        assert connection.execute(
            "SELECT workspace_id FROM account_events "
            "WHERE id = 'ambiguous-account-event'"
        ).fetchone() == (None,)

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE mobile_service_requests SET progress_percent = 101 "
                "WHERE id = 'mapped-request'"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE mobile_service_requests SET status = 'teleported' "
                "WHERE id = 'mapped-request'"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE mobile_service_requests "
                "SET organization_id = NULL, workspace_id = NULL, "
                "idempotency_key = 'unsafe-key', "
                "request_sha256 = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' "
                "WHERE id = 'mapped-request'"
            )
        connection.rollback()

        # Workspace deletion intentionally uses ON DELETE SET NULL. Keyed
        # history must remain structurally valid during that transition while
        # organization ownership and the payload digest stay pinned.
        connection.execute(
            "UPDATE mobile_service_requests "
            "SET workspace_id = NULL, idempotency_key = 'retained-key', "
            "request_sha256 = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' "
            "WHERE id = 'mapped-request'"
        )
        assert connection.execute(
            "SELECT organization_id, workspace_id, length(request_sha256) "
            "FROM mobile_service_requests WHERE id = 'mapped-request'"
        ).fetchone() == ("journey-org", None, 64)
        connection.rollback()

    _alembic(
        backend_dir,
        database_path,
        "downgrade",
        "integration_registry_v1",
    )
    with sqlite3.connect(database_path) as connection:
        assert "organization_id" not in _columns(connection, "mobile_service_requests")
        assert "workspace_id" not in _columns(connection, "account_events")
        assert connection.execute(
            "SELECT status, progress_percent FROM mobile_service_requests "
            "WHERE id = 'mapped-request'"
        ).fetchone() == ("completed", 100)

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT organization_id, workspace_id, asset_id "
            "FROM mobile_service_requests WHERE id = 'mapped-request'"
        ).fetchone() == (
            "journey-org",
            "journey-workspace",
            "journey-asset",
        )
