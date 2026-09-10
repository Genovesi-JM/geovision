from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys


TABLES = {
    "notifications",
    "notification_event_links",
    "notification_deliveries",
    "notification_preferences",
    "notification_endpoints",
}


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


def _indexes(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA index_list({table})")}


def test_notification_delivery_migration_round_trip(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "phase-20.sqlite3"

    _alembic(backend_dir, database_path, "upgrade", "report_engine_v1")
    with sqlite3.connect(database_path) as connection:
        assert TABLES.isdisjoint(_tables(connection))
        assert "account_events" in _tables(connection)
        assert "alert_notifications" in _tables(connection)

    _alembic(backend_dir, database_path, "upgrade", "notification_delivery_v1")
    with sqlite3.connect(database_path) as connection:
        assert TABLES.issubset(_tables(connection))
        assert {
            "organization_id",
            "workspace_id",
            "recipient_user_id",
            "recipient_kind",
            "recipient_key",
            "notification_type",
            "severity",
            "target_type",
            "target_id",
            "correlation_id",
            "deduplication_key",
            "aggregation_key",
            "occurrence_count",
            "aggregation_window_ends_at",
            "read_at",
        }.issubset(_columns(connection, "notifications"))
        assert {
            "notification_id",
            "endpoint_id",
            "channel",
            "provider",
            "status",
            "idempotency_key",
            "payload_ciphertext",
            "payload_key_id",
            "payload_sha256",
            "attempts",
            "max_attempts",
            "next_attempt_at",
            "claimed_by",
            "claimed_at",
            "lease_expires_at",
            "provider_message_id",
            "last_error_code",
            "last_error_message",
            "delivered_at",
            "dead_lettered_at",
        }.issubset(_columns(connection, "notification_deliveries"))
        assert {
            "ix_notifications_recipient_inbox",
            "ix_notifications_aggregation_window",
        }.issubset(_indexes(connection, "notifications"))
        assert {
            "ix_notification_deliveries_due",
            "ix_notification_deliveries_claim",
            "ix_notification_deliveries_idempotency_key",
        }.issubset(_indexes(connection, "notification_deliveries"))
        assert {
            "installation_id",
            "handle_ciphertext",
            "handle_digest",
            "encryption_key_id",
            "lifecycle_version",
        }.issubset(_columns(connection, "notification_endpoints"))
        assert {
            "scope_key",
            "category",
            "in_app_enabled",
            "push_enabled",
            "email_enabled",
            "sms_enabled",
            "minimum_severity",
            "quiet_hours_start",
            "quiet_hours_end",
            "timezone",
        }.issubset(_columns(connection, "notification_preferences"))

        notification_columns = _columns(connection, "notifications")
        assert "deep_link" not in notification_columns
        assert "url" not in notification_columns

    _alembic(backend_dir, database_path, "downgrade", "report_engine_v1")
    with sqlite3.connect(database_path) as connection:
        assert TABLES.isdisjoint(_tables(connection))
        assert "reports" in _tables(connection)
        assert "account_events" in _tables(connection)
        assert "alert_notifications" in _tables(connection)

    _alembic(backend_dir, database_path, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert TABLES.issubset(_tables(connection))
