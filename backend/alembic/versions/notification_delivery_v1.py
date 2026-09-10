"""Add the durable notification inbox and external-delivery ledger.

Revision ID: notification_delivery_v1
Revises: report_engine_v1
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "notification_delivery_v1"
down_revision = "report_engine_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=True),
        sa.Column("recipient_user_id", sa.String(36), nullable=True),
        sa.Column("recipient_kind", sa.String(20), nullable=False),
        sa.Column("recipient_key", sa.String(200), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("notification_type", sa.String(100), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="INFO"),
        sa.Column("target_type", sa.String(30), nullable=False, server_default="NONE"),
        sa.Column("target_id", sa.String(100), nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=True),
        sa.Column("deduplication_key", sa.String(240), nullable=False),
        sa.Column("aggregation_key", sa.String(240), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "first_occurred_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "last_occurred_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("aggregation_window_ends_at", sa.DateTime(), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "recipient_kind IN ('USER', 'PRE_ACCOUNT')",
            name="ck_notification_recipient_kind",
        ),
        sa.CheckConstraint(
            "(recipient_kind = 'USER' AND recipient_user_id IS NOT NULL) OR "
            "(recipient_kind = 'PRE_ACCOUNT' AND recipient_user_id IS NULL)",
            name="ck_notification_recipient_identity",
        ),
        sa.CheckConstraint(
            "severity IN ('INFO', 'WATCH', 'WARNING', 'CRITICAL')",
            name="ck_notification_severity",
        ),
        sa.CheckConstraint(
            "target_type IN ('NONE', 'ASSET', 'REPORT', 'ACTION', 'ORDER', "
            "'SHIPMENT', 'INVITATION', 'SERVICE')",
            name="ck_notification_target_type",
        ),
        sa.CheckConstraint(
            "(target_type = 'NONE' AND target_id IS NULL) OR "
            "(target_type <> 'NONE' AND target_id IS NOT NULL)",
            name="ck_notification_typed_target",
        ),
        sa.CheckConstraint(
            "occurrence_count > 0", name="ck_notification_occurrence_count"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["companies.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["accounts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "recipient_key",
            "deduplication_key",
            name="uq_notification_recipient_deduplication",
        ),
    )
    for column in (
        "organization_id",
        "workspace_id",
        "recipient_user_id",
        "recipient_key",
        "category",
        "notification_type",
        "severity",
        "target_type",
        "correlation_id",
        "aggregation_key",
        "last_occurred_at",
        "aggregation_window_ends_at",
        "read_at",
        "created_at",
    ):
        op.create_index(f"ix_notifications_{column}", "notifications", [column])
    op.create_index(
        "ix_notifications_recipient_inbox",
        "notifications",
        ["recipient_user_id", "read_at", "last_occurred_at"],
    )
    op.create_index(
        "ix_notifications_scope_recipient",
        "notifications",
        ["organization_id", "workspace_id", "recipient_key"],
    )
    op.create_index(
        "ix_notifications_aggregation_window",
        "notifications",
        [
            "organization_id",
            "recipient_key",
            "aggregation_key",
            "aggregation_window_ends_at",
        ],
    )

    op.create_table(
        "notification_event_links",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("notification_id", sa.String(36), nullable=False),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("recipient_key", sa.String(200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["notifications.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["operational_domain_events.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id", "recipient_key", name="uq_notification_event_recipient"
        ),
        sa.UniqueConstraint(
            "notification_id", "event_id", name="uq_notification_event_link"
        ),
    )
    op.create_index(
        "ix_notification_event_links_notification_id",
        "notification_event_links",
        ["notification_id"],
    )
    op.create_index(
        "ix_notification_event_links_event_id",
        "notification_event_links",
        ["event_id"],
    )

    op.create_table(
        "notification_endpoints",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=True),
        sa.Column("installation_id", sa.String(200), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("handle_ciphertext", sa.Text(), nullable=False),
        sa.Column("handle_digest", sa.String(64), nullable=False),
        sa.Column("encryption_key_id", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "last_registered_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("lifecycle_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "platform IN ('IOS', 'ANDROID', 'WEB')",
            name="ck_notification_endpoint_platform",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DISABLED', 'REVOKED')",
            name="ck_notification_endpoint_status",
        ),
        sa.CheckConstraint(
            "lifecycle_version > 0", name="ck_notification_endpoint_version"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["companies.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("installation_id"),
        sa.UniqueConstraint(
            "provider", "handle_digest", name="uq_notification_endpoint_provider_handle"
        ),
    )
    for column in ("user_id", "organization_id", "platform", "provider", "status"):
        op.create_index(
            f"ix_notification_endpoints_{column}", "notification_endpoints", [column]
        )
    op.create_index(
        "ix_notification_endpoints_user_status",
        "notification_endpoints",
        ["user_id", "status"],
    )

    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=True),
        sa.Column("scope_key", sa.String(40), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("in_app_enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("push_enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("sms_enabled", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("minimum_severity", sa.String(20), nullable=False, server_default="INFO"),
        sa.Column("quiet_hours_start", sa.String(5), nullable=True),
        sa.Column("quiet_hours_end", sa.String(5), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "minimum_severity IN ('INFO', 'WATCH', 'WARNING', 'CRITICAL')",
            name="ck_notification_preference_severity",
        ),
        sa.CheckConstraint(
            "(organization_id IS NULL AND scope_key = 'GLOBAL') OR "
            "(organization_id IS NOT NULL AND scope_key = organization_id)",
            name="ck_notification_preference_scope",
        ),
        sa.CheckConstraint(
            "(quiet_hours_start IS NULL AND quiet_hours_end IS NULL) OR "
            "(quiet_hours_start IS NOT NULL AND quiet_hours_end IS NOT NULL)",
            name="ck_notification_preference_quiet_hours",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["companies.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "scope_key",
            "category",
            name="uq_notification_preference_scope_category",
        ),
    )
    for column in ("user_id", "organization_id", "category"):
        op.create_index(
            f"ix_notification_preferences_{column}",
            "notification_preferences",
            [column],
        )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("notification_id", sa.String(36), nullable=False),
        sa.Column("endpoint_id", sa.String(36), nullable=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("idempotency_key", sa.String(240), nullable=False),
        sa.Column("payload_ciphertext", sa.Text(), nullable=True),
        sa.Column("payload_key_id", sa.String(100), nullable=True),
        sa.Column("payload_sha256", sa.String(64), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("claimed_by", sa.String(100), nullable=True),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("provider_message_id", sa.String(200), nullable=True),
        sa.Column("last_error_code", sa.String(80), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("dead_lettered_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "channel IN ('PUSH', 'EMAIL', 'SMS')",
            name="ck_notification_delivery_channel",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'RETRY', 'DELIVERED', "
            "'SUPPRESSED', 'DEAD_LETTER')",
            name="ck_notification_delivery_status",
        ),
        sa.CheckConstraint(
            "attempts >= 0", name="ck_notification_delivery_attempts"
        ),
        sa.CheckConstraint(
            "max_attempts > 0", name="ck_notification_delivery_max_attempts"
        ),
        sa.CheckConstraint(
            "(payload_ciphertext IS NULL AND payload_key_id IS NULL AND "
            "payload_sha256 IS NULL) OR (payload_ciphertext IS NOT NULL AND "
            "payload_key_id IS NOT NULL AND payload_sha256 IS NOT NULL)",
            name="ck_notification_delivery_encrypted_payload",
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["notifications.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["endpoint_id"], ["notification_endpoints.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "notification_id",
        "endpoint_id",
        "channel",
        "provider",
        "status",
        "next_attempt_at",
        "created_at",
    ):
        op.create_index(
            f"ix_notification_deliveries_{column}",
            "notification_deliveries",
            [column],
        )
    op.create_index(
        "ix_notification_deliveries_idempotency_key",
        "notification_deliveries",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_notification_deliveries_due",
        "notification_deliveries",
        ["status", "next_attempt_at", "created_at"],
    )
    op.create_index(
        "ix_notification_deliveries_notification_channel",
        "notification_deliveries",
        ["notification_id", "channel", "status"],
    )
    op.create_index(
        "ix_notification_deliveries_claim",
        "notification_deliveries",
        ["status", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_table("notification_deliveries")
    op.drop_table("notification_preferences")
    op.drop_table("notification_endpoints")
    op.drop_table("notification_event_links")
    op.drop_table("notifications")
