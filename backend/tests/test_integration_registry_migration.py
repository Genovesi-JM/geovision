from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from app.models import (
    FeatureFlagOverride,
    IntegrationConnection,
    IntegrationSyncEvent,
    IntegrationSyncRun,
)


def _alembic(
    backend_dir: Path, database_path: Path, command: str, revision: str
) -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": f"sqlite:///{database_path}",
            "ENV": "test",
            "STARTUP_COMPATIBILITY_BOOTSTRAP": "false",
        }
    )
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", command, revision],
        cwd=backend_dir,
        env=environment,
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


def _indexes(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA index_list({table})")}


def _foreign_key_groups(
    connection: sqlite3.Connection,
    table: str,
) -> set[tuple[tuple[str, ...], str, tuple[str, ...], str]]:
    groups: dict[int, list[tuple[int, str, str, str, str]]] = {}
    for row in connection.execute(f"PRAGMA foreign_key_list({table})"):
        groups.setdefault(row[0], []).append((row[1], row[3], row[2], row[4], row[6]))
    return {
        (
            tuple(item[1] for item in sorted(group)),
            sorted(group)[0][2],
            tuple(item[3] for item in sorted(group)),
            sorted(group)[0][4],
        )
        for group in groups.values()
    }


def _seed_legacy_scope(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        INSERT INTO companies (
            id, name, email, country, organization_type, timezone, sectors, status,
            subscription_plan, max_users, max_sites, max_storage_gb,
            current_users, current_sites, storage_used_gb, created_at, updated_at
        ) VALUES
            ('org-one', 'One', 'one@example.test', 'Spain', 'customer', 'UTC', '[]',
             'active', 'custom', 10, 10, 10, 1, 1, 0, CURRENT_TIMESTAMP,
             CURRENT_TIMESTAMP),
            ('org-two', 'Two', 'two@example.test', 'Spain', 'customer', 'UTC', '[]',
             'active', 'custom', 10, 10, 10, 1, 1, 0, CURRENT_TIMESTAMP,
             CURRENT_TIMESTAMP);

        INSERT INTO users (
            id, email, role, is_active, auth_generation, created_at, updated_at
        ) VALUES
            ('user-one', 'member-one@example.test', 'client', 1, 0,
             CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('user-two', 'member-two@example.test', 'client', 1, 0,
             CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

        INSERT INTO accounts (
            id, organization_id, name, sector_focus, entity_type, customer_type,
            dashboard_profile, use_cases, modules_enabled, status, created_at,
            updated_at
        ) VALUES
            ('workspace-one', 'org-one', 'Workspace one', 'agriculture',
             'company', 'farm', 'farm', '[]', '[]', 'active',
             CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('workspace-two', 'org-two', 'Workspace two', 'infrastructure',
             'company', 'infrastructure', 'infrastructure', '[]', '[]',
             'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

        INSERT INTO account_members (
            account_id, user_id, role, status, created_at, updated_at
        ) VALUES
            ('workspace-one', 'user-one', 'owner', 'active', CURRENT_TIMESTAMP,
             CURRENT_TIMESTAMP),
            ('workspace-two', 'user-two', 'owner', 'active', CURRENT_TIMESTAMP,
             CURRENT_TIMESTAMP);

        INSERT INTO connectors (
            id, company_id, connector_type, name, config_json, enabled,
            sync_status, created_at
        ) VALUES (
            'legacy-connector', 'org-one', 'legacy', 'Preserved connector', '{}',
            1, 'never', CURRENT_TIMESTAMP
        );

        INSERT INTO integrations (
            id, company_id, connector_type, name, is_active,
            auto_sync_enabled, sync_interval_hours, sync_status, created_at
        ) VALUES (
            'legacy-integration', 'org-one', 'odoo', 'Preserved integration', 1,
            1, 24, 'never', CURRENT_TIMESTAMP
        );
        """
    )
    connection.commit()


def _insert_valid_registry_rows(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO integration_connections (
            id, organization_id, workspace_id, user_id, connection_key,
            provider_family, provider_code, display_name, status, enabled,
            endpoint_url, configuration_reference, settings_json,
            credential_reference, webhook_secret_reference, capabilities_json,
            lifecycle_version, created_at, updated_at
        ) VALUES (
            'connection-one', 'org-one', 'workspace-one', 'user-one',
            'odoo-primary', 'ERP', 'ODOO', 'Primary Odoo', 'ACTIVE', 1,
            'https://odoo.example.test/json/2',
            'azure-app-configuration://geovision/odoo-primary',
            '{"database":"geovision"}',
            'azure-key-vault://geovision/odoo-api-key',
            'https://geovision.vault.azure.net/secrets/odoo-webhook/v1',
            '["orders.read","orders.write"]', 1, CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        INSERT INTO integration_sync_runs (
            id, connection_id, organization_id, workspace_id, direction,
            operation, trigger_type, status, idempotency_key, payload_sha256,
            attempt_count, max_attempts, lifecycle_version, created_at, updated_at
        ) VALUES (
            'run-one', 'connection-one', 'org-one', 'workspace-one', 'OUTBOUND',
            'ORDER_EXPORT', 'EVENT', 'PENDING', 'run-idempotency', ?, 0, 3, 1,
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        """,
        ("a" * 64,),
    )
    connection.execute(
        """
        INSERT INTO integration_sync_events (
            id, run_id, connection_id, organization_id, workspace_id,
            direction, operation, resource_type, resource_id,
            external_reference, idempotency_key, payload_sha256, status,
            attempt_count, max_attempts, lifecycle_version, created_at, updated_at
        ) VALUES (
            'event-one', 'run-one', 'connection-one', 'org-one',
            'workspace-one', 'OUTBOUND', 'UPSERT', 'ORDER', 'order-one',
            'odoo-order-42', 'event-idempotency', ?, 'PENDING', 0, 3, 1,
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        """,
        ("b" * 64,),
    )
    connection.execute(
        """
        INSERT INTO feature_flag_overrides (
            id, organization_id, workspace_id, user_id, flag_key, enabled,
            source, configuration_reference, etag, configuration_version,
            lifecycle_version, created_at, updated_at
        ) VALUES
            ('workspace-flag', 'org-one', 'workspace-one', NULL,
             'integrations.odoo', 1, 'AZURE_APP_CONFIGURATION',
             'azure-app-configuration://feature/integrations.odoo', 'etag-1',
             '42', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('user-flag', 'org-one', 'workspace-one', 'user-one',
             'integrations.odoo', 0, 'GEOVISION', NULL, NULL, NULL, 1,
             CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
    )
    connection.commit()


def test_integration_registry_migration_round_trip_and_constraints(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "integration-registry.sqlite3"
    _alembic(backend_dir, database_path, "upgrade", "trust_economics_v1")

    with sqlite3.connect(database_path) as connection:
        _seed_legacy_scope(connection)

    _alembic(backend_dir, database_path, "upgrade", "integration_registry_v1")
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        assert {
            "integration_connections",
            "integration_sync_runs",
            "integration_sync_events",
            "feature_flag_overrides",
        }.issubset(_tables(connection))
        assert {
            "credential_reference",
            "webhook_secret_reference",
            "health_status",
            "rate_limit_remaining",
            "circuit_breaker_state",
            "disconnected_by_user_id",
            "disconnected_at",
            "lifecycle_version",
        }.issubset(_columns(connection, "integration_connections"))
        assert {
            "direction",
            "operation",
            "idempotency_key",
            "payload_sha256",
            "attempt_count",
            "next_retry_at",
            "failure_summary",
        }.issubset(_columns(connection, "integration_sync_runs"))
        assert {
            "resource_type",
            "resource_id",
            "external_reference",
            "processed_at",
        }.issubset(_columns(connection, "integration_sync_events"))
        assert {
            "source",
            "configuration_reference",
            "etag",
            "configuration_version",
            "lifecycle_version",
        }.issubset(_columns(connection, "feature_flag_overrides"))
        assert {
            "uq_feature_flag_override_workspace_flag",
            "uq_feature_flag_override_user_flag",
            "ix_feature_flag_override_lookup",
        }.issubset(_indexes(connection, "feature_flag_overrides"))
        assert (
            ("workspace_id", "organization_id"),
            "accounts",
            ("id", "organization_id"),
            "RESTRICT",
        ) in _foreign_key_groups(connection, "integration_connections")
        assert (
            ("workspace_id", "user_id"),
            "account_members",
            ("account_id", "user_id"),
            "CASCADE",
        ) in _foreign_key_groups(connection, "feature_flag_overrides")

        _insert_valid_registry_rows(connection)
        assert connection.execute(
            "SELECT provider_family, provider_code, settings_json "
            "FROM integration_connections WHERE id = 'connection-one'"
        ).fetchone() == ("ERP", "ODOO", '{"database":"geovision"}')
        assert connection.execute(
            "SELECT COUNT(*) FROM integration_sync_events"
        ).fetchone() == (1,)

        # User-scoped connections and the normalized sync ledger are durable;
        # removing their scope or parent rows must be an explicit lifecycle
        # operation rather than an accidental cascade.
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM account_members "
                "WHERE account_id = 'workspace-one' AND user_id = 'user-one'"
            )
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM integration_sync_runs WHERE id = 'run-one'")
        connection.rollback()

        invalid_connections = (
            (
                "cross-org",
                "org-two",
                "workspace-one",
                None,
                "cross-org",
                "ERP",
                "ODOO",
                "Cross org",
                "CONFIGURING",
                0,
                None,
                "{}",
                None,
            ),
            (
                "non-member",
                "org-one",
                "workspace-one",
                "user-two",
                "non-member",
                "ERP",
                "ODOO",
                "Non-member",
                "CONFIGURING",
                0,
                None,
                "{}",
                None,
            ),
            (
                "unsafe-endpoint",
                "org-one",
                None,
                None,
                "unsafe-endpoint",
                "ERP",
                "ODOO",
                "Unsafe endpoint",
                "CONFIGURING",
                0,
                "https://user:password@odoo.example.test",
                "{}",
                None,
            ),
            (
                "raw-secret-reference",
                "org-one",
                None,
                None,
                "raw-secret-reference",
                "ERP",
                "ODOO",
                "Raw secret",
                "CONFIGURING",
                0,
                None,
                "{}",
                "plaintext-api-key",
            ),
            (
                "secret-settings",
                "org-one",
                None,
                None,
                "secret-settings",
                "ERP",
                "ODOO",
                "Secret settings",
                "CONFIGURING",
                0,
                None,
                '{"api_key":"plaintext"}',
                None,
            ),
            (
                "invalid-disconnect",
                "org-one",
                None,
                None,
                "invalid-disconnect",
                "ERP",
                "ODOO",
                "Invalid disconnect",
                "DISCONNECTED",
                0,
                None,
                "{}",
                None,
            ),
        )
        for row in invalid_connections:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO integration_connections (
                        id, organization_id, workspace_id, user_id,
                        connection_key, provider_family, provider_code,
                        display_name, status, enabled, endpoint_url,
                        settings_json, credential_reference, capabilities_json,
                        lifecycle_version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', 1,
                              CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    row,
                )
            connection.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO feature_flag_overrides (
                    id, organization_id, workspace_id, user_id, flag_key,
                    enabled, source, lifecycle_version, created_at, updated_at
                ) VALUES (
                    'foreign-user-flag', 'org-one', 'workspace-one', 'user-two',
                    'integrations.odoo', 1, 'GEOVISION', 1, CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                """
            )
        connection.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO feature_flag_overrides (
                    id, organization_id, workspace_id, user_id, flag_key,
                    enabled, source, configuration_reference,
                    lifecycle_version, created_at, updated_at
                ) VALUES (
                    'unbound-azure-flag', 'org-one', 'workspace-one', NULL,
                    'integrations.azure', 1, 'AZURE_APP_CONFIGURATION', NULL, 1,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        connection.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO feature_flag_overrides (
                    id, organization_id, workspace_id, user_id, flag_key,
                    enabled, source, lifecycle_version, created_at, updated_at
                ) VALUES (
                    'duplicate-workspace-flag', 'org-one', 'workspace-one', NULL,
                    'integrations.odoo', 0, 'GEOVISION', 1, CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                """
            )
        connection.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO integration_sync_events (
                    id, run_id, connection_id, organization_id, workspace_id,
                    direction, operation, resource_type, resource_id,
                    external_reference, idempotency_key, payload_sha256, status,
                    attempt_count, max_attempts, lifecycle_version, created_at,
                    updated_at
                ) VALUES (
                    'unsafe-event', 'run-one', 'connection-one', 'org-one',
                    'workspace-one', 'OUTBOUND', 'UPSERT', 'ORDER', 'order-one',
                    'https://odoo.example.test/order/42', 'unsafe-event', ?,
                    'PENDING', 0, 3, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """,
                ("c" * 64,),
            )
        connection.rollback()

    _alembic(backend_dir, database_path, "downgrade", "trust_economics_v1")
    with sqlite3.connect(database_path) as connection:
        assert "integration_connections" not in _tables(connection)
        assert "integration_sync_runs" not in _tables(connection)
        assert "integration_sync_events" not in _tables(connection)
        assert "feature_flag_overrides" not in _tables(connection)
        assert connection.execute(
            "SELECT name FROM connectors WHERE id = 'legacy-connector'"
        ).fetchone() == ("Preserved connector",)
        assert connection.execute(
            "SELECT name FROM integrations WHERE id = 'legacy-integration'"
        ).fetchone() == ("Preserved integration",)

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert {
            "integration_connections",
            "integration_sync_runs",
            "integration_sync_events",
            "feature_flag_overrides",
        }.issubset(_tables(connection))
        assert connection.execute(
            "SELECT name FROM integrations WHERE id = 'legacy-integration'"
        ).fetchone() == ("Preserved integration",)


def test_integration_registry_models_reject_secret_material_and_normalize_keys():
    connection = IntegrationConnection(
        organization_id="org-one",
        connection_key=" Odoo.Primary ",
        provider_family="erp",
        provider_code="odoo",
        display_name="Odoo",
        endpoint_url="https://odoo.example.test/json/2",
        settings_json={"database": "geovision", "timeout_profile": "standard"},
        credential_reference="azure-key-vault://geovision/odoo-api-key",
        capabilities_json=["orders.write", "orders.read", "orders.write"],
    )
    assert connection.connection_key == "odoo.primary"
    assert connection.provider_family == "ERP"
    assert connection.provider_code == "ODOO"
    assert (
        connection.settings_json
        == '{"database":"geovision","timeout_profile":"standard"}'
    )
    assert connection.capabilities_json == '["orders.read","orders.write"]'

    workspace_flag = FeatureFlagOverride(
        organization_id="org-one",
        workspace_id="workspace-one",
        flag_key=" Integrations.Odoo ",
        enabled=True,
    )
    assert workspace_flag.flag_key == "integrations.odoo"

    with pytest.raises(ValueError, match="credentials or secret"):
        IntegrationConnection(
            organization_id="org-one",
            connection_key="unsafe-settings",
            provider_family="ERP",
            provider_code="ODOO",
            display_name="Unsafe",
            settings_json={"api_key": "plaintext"},
        )
    with pytest.raises(ValueError, match="without userinfo"):
        IntegrationConnection(
            organization_id="org-one",
            connection_key="unsafe-endpoint",
            provider_family="ERP",
            provider_code="ODOO",
            display_name="Unsafe",
            endpoint_url="https://user:password@odoo.example.test",
        )
    with pytest.raises(ValueError, match="secret-manager references"):
        IntegrationConnection(
            organization_id="org-one",
            connection_key="unsafe-secret",
            provider_family="ERP",
            provider_code="ODOO",
            display_name="Unsafe",
            credential_reference="plaintext-token",
        )
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        IntegrationSyncRun(
            connection_id="connection-one",
            organization_id="org-one",
            direction="OUTBOUND",
            operation="ORDER_EXPORT",
            trigger_type="EVENT",
            idempotency_key="run-one",
            payload_sha256="not-a-hash",
        )
    with pytest.raises(ValueError, match="opaque provider identifier"):
        IntegrationSyncEvent(
            run_id="run-one",
            connection_id="connection-one",
            organization_id="org-one",
            direction="OUTBOUND",
            operation="UPSERT",
            idempotency_key="event-one",
            payload_sha256="a" * 64,
            external_reference="https://provider.example.test/resource/42",
        )

    connection_columns = set(IntegrationConnection.__table__.columns.keys())
    assert not connection_columns.intersection(
        {
            "api_key",
            "api_secret",
            "access_token",
            "refresh_token",
            "password",
            "secret_value",
        }
    )
    assert {"credential_reference", "webhook_secret_reference"} <= connection_columns
