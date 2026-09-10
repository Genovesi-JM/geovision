from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def _alembic(backend_dir: Path, database_path: Path, command: str, revision: str) -> None:
    env = os.environ.copy()
    env["ENV"] = "test"
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


def _indexes(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA index_list({table})")}


def _foreign_keys(connection: sqlite3.Connection, table: str) -> set[tuple[str, str, str]]:
    return {
        (row[3], row[2], row[6])
        for row in connection.execute(f"PRAGMA foreign_key_list({table})")
    }


def _unique_index_columns(connection: sqlite3.Connection, table: str) -> set[tuple[str, ...]]:
    result: set[tuple[str, ...]] = set()
    for row in connection.execute(f"PRAGMA index_list({table})"):
        if not row[2]:
            continue
        columns = tuple(
            value[2]
            for value in connection.execute(f"PRAGMA index_info('{row[1]}')")
        )
        result.add(columns)
    return result


def test_trust_economics_migration_backfills_and_round_trips(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "trust-economics.sqlite3"
    _alembic(backend_dir, database_path, "upgrade", "odoo_erp_v1")

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO audit_log (
                id, user_id, user_email, action, resource_type, resource_id,
                details, ip_address, user_agent, created_at
            ) VALUES (
                'legacy-audit', NULL, NULL, 'legacy.action', 'legacy_resource',
                'legacy-resource', '{"preserve":true}', NULL, NULL,
                CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            INSERT INTO reports (
                id, organization_id, workspace_id, asset_id, acquisition_id,
                report_type, title, template_version, revision, status, qa_level,
                context_schema_version, context_json, context_sha256,
                narrative_provider, narrative_model, narrative_schema_version,
                narrative_json, qa_result_json, output_dataset_id, output_file_id,
                supersedes_report_id, generation_key, lifecycle_version,
                created_at, updated_at
            ) VALUES (
                'legacy-report', 'legacy-org', NULL, 'legacy-asset', NULL,
                'SITE_REPORT', 'Preserved report', 'v1', 1, 'DRAFT',
                'HUMAN_REVIEW', 'context-v1', '{}',
                '0000000000000000000000000000000000000000000000000000000000000000',
                'deterministic', NULL, 'narrative-v1', '{}', '{}', NULL, NULL,
                NULL, 'legacy-generation-key', 1, CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            INSERT INTO kpi_values (
                id, kpi_definition_id, account_id, organization_id,
                workspace_id, asset_id, site_id, dataset_id, mission_id, value,
                numeric_value, status, confidence, measured_at, source,
                algorithm_version, provenance_json, is_baseline, recorded_at,
                created_at
            ) VALUES (
                'legacy-kpi', 'legacy-definition', 'legacy-account', NULL, NULL,
                NULL, NULL, 'missing-dataset', NULL, '42', 42, 'GOOD', 1,
                CURRENT_TIMESTAMP, 'legacy', 'legacy-1', '{}', 0,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()

    _alembic(backend_dir, database_path, "upgrade", "trust_economics_v1")
    with sqlite3.connect(database_path) as connection:
        assert {"provider_usage", "internal_costs"}.issubset(_tables(connection))
        assert {
            "organization_id",
            "workspace_id",
            "request_id",
            "correlation_id",
            "outcome",
        }.issubset(_columns(connection, "audit_log"))
        assert {
            "provenance_json",
            "narrative_model_version",
        }.issubset(_columns(connection, "reports"))
        assert {
            "dataset_id",
            "fulfilment_job_id",
            "intelligence_acquisition_id",
            "notification_delivery_id",
        }.issubset(_columns(connection, "provider_usage"))
        assert {
            "ix_audit_log_organization_id",
            "ix_audit_log_workspace_id",
            "ix_audit_log_request_id",
            "ix_audit_log_correlation_id",
            "ix_audit_log_outcome",
        }.issubset(_indexes(connection, "audit_log"))
        assert "ix_kpi_values_dataset_id" in _indexes(connection, "kpi_values")
        assert (
            "dataset_id",
            "datasets",
            "SET NULL",
        ) in _foreign_keys(connection, "kpi_values")
        assert (
            "organization_id",
            "idempotency_key",
        ) in _unique_index_columns(connection, "provider_usage")
        assert (
            "organization_id",
            "idempotency_key",
        ) in _unique_index_columns(connection, "internal_costs")
        assert connection.execute(
            "SELECT details, outcome FROM audit_log WHERE id = 'legacy-audit'"
        ).fetchone() == ('{"preserve":true}', "UNKNOWN")
        assert connection.execute(
            "SELECT provenance_json, narrative_model_version FROM reports "
            "WHERE id = 'legacy-report'"
        ).fetchone() == ("{}", "legacy-unversioned")
        assert connection.execute(
            "SELECT dataset_id FROM kpi_values WHERE id = 'legacy-kpi'"
        ).fetchone() == (None,)

    _alembic(backend_dir, database_path, "downgrade", "odoo_erp_v1")
    with sqlite3.connect(database_path) as connection:
        assert "provider_usage" not in _tables(connection)
        assert "internal_costs" not in _tables(connection)
        assert "outcome" not in _columns(connection, "audit_log")
        assert "provenance_json" not in _columns(connection, "reports")
        assert connection.execute(
            "SELECT details FROM audit_log WHERE id = 'legacy-audit'"
        ).fetchone() == ('{"preserve":true}',)
        assert connection.execute(
            "SELECT title FROM reports WHERE id = 'legacy-report'"
        ).fetchone() == ("Preserved report",)

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert {"provider_usage", "internal_costs"}.issubset(_tables(connection))
        assert connection.execute(
            "SELECT outcome FROM audit_log WHERE id = 'legacy-audit'"
        ).fetchone() == ("UNKNOWN",)
