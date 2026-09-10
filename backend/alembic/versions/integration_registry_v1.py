"""Add the tenant-scoped integration registry and feature overrides.

Revision ID: integration_registry_v1
Revises: trust_economics_v1
"""

from alembic import op
import sqlalchemy as sa


revision = "integration_registry_v1"
down_revision = "trust_economics_v1"
branch_labels = None
depends_on = None


_SECRET_REFERENCE_CHECK = """(
    {column} IS NULL OR (
        (
            {column} LIKE 'azure-key-vault://%'
            OR {column} LIKE 'keyvault://%'
            OR {column} LIKE 'vault://%'
            OR {column} LIKE 'secret://%'
            OR {column} LIKE 'env://%'
            OR {column} LIKE 'aws-secrets-manager://%'
            OR {column} LIKE 'gcp-secret-manager://%'
            OR {column} LIKE 'https://%.vault.azure.net/secrets/%'
        )
        AND {column} NOT LIKE '%://%@%'
        AND {column} NOT LIKE '%?%'
        AND {column} NOT LIKE '%#%'
    )
)"""


def upgrade() -> None:
    # The primary key already guarantees this pair is unique. The explicit
    # constraint gives new tables a portable composite FK that also binds a
    # workspace to its canonical organization.
    with op.batch_alter_table("accounts") as batch:
        batch.create_unique_constraint(
            "uq_accounts_id_organization",
            ["id", "organization_id"],
        )

    op.create_table(
        "integration_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=True),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("connection_key", sa.String(120), nullable=False),
        sa.Column("provider_family", sa.String(80), nullable=False),
        sa.Column("provider_code", sa.String(80), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column(
            "status",
            sa.String(24),
            nullable=False,
            server_default="CONFIGURING",
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("endpoint_url", sa.String(1000), nullable=True),
        sa.Column("configuration_reference", sa.String(500), nullable=True),
        sa.Column("settings_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("credential_reference", sa.String(1000), nullable=True),
        sa.Column("webhook_secret_reference", sa.String(1000), nullable=True),
        sa.Column("capabilities_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("last_sync_started_at", sa.DateTime(), nullable=True),
        sa.Column("last_sync_succeeded_at", sa.DateTime(), nullable=True),
        sa.Column("last_sync_failed_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_code", sa.String(80), nullable=True),
        sa.Column("last_error_summary", sa.String(500), nullable=True),
        sa.Column(
            "health_status",
            sa.String(20),
            nullable=False,
            server_default="UNKNOWN",
        ),
        sa.Column("health_checked_at", sa.DateTime(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column(
            "retry_max_attempts", sa.Integer(), nullable=False, server_default="3"
        ),
        sa.Column(
            "retry_base_seconds", sa.Integer(), nullable=False, server_default="30"
        ),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=True),
        sa.Column("rate_limit_remaining", sa.Integer(), nullable=True),
        sa.Column("rate_limit_reset_at", sa.DateTime(), nullable=True),
        sa.Column(
            "circuit_breaker_state",
            sa.String(20),
            nullable=False,
            server_default="CLOSED",
        ),
        sa.Column(
            "circuit_breaker_failure_threshold",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
        sa.Column(
            "circuit_breaker_failure_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("circuit_breaker_opened_at", sa.DateTime(), nullable=True),
        sa.Column(
            "lifecycle_version", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(36), nullable=True),
        sa.Column("disconnected_by_user_id", sa.String(36), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("disconnected_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["companies.id"],
            name="fk_integration_connection_organization",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "organization_id"],
            ["accounts.id", "accounts.organization_id"],
            name="fk_integration_connection_workspace_org",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["account_members.account_id", "account_members.user_id"],
            name="fk_integration_connection_workspace_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_integration_connection_created_by",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name="fk_integration_connection_updated_by",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["disconnected_by_user_id"],
            ["users.id"],
            name="fk_integration_connection_disconnected_by",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "connection_key",
            name="uq_integration_connection_org_key",
        ),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            name="uq_integration_connection_id_org",
        ),
        sa.CheckConstraint(
            "length(trim(connection_key)) > 0 AND connection_key = lower(connection_key)",
            name="ck_integration_connection_key",
        ),
        sa.CheckConstraint(
            "length(trim(provider_family)) > 0 AND provider_family = upper(provider_family)",
            name="ck_integration_connection_provider_family",
        ),
        sa.CheckConstraint(
            "length(trim(provider_code)) > 0 AND provider_code = upper(provider_code)",
            name="ck_integration_connection_provider_code",
        ),
        sa.CheckConstraint(
            "status IN ('CONFIGURING', 'ACTIVE', 'DEGRADED', 'DISCONNECTED')",
            name="ck_integration_connection_status",
        ),
        sa.CheckConstraint(
            "health_status IN ('UNKNOWN', 'HEALTHY', 'DEGRADED', 'UNHEALTHY')",
            name="ck_integration_connection_health",
        ),
        sa.CheckConstraint(
            "circuit_breaker_state IN ('CLOSED', 'OPEN', 'HALF_OPEN')",
            name="ck_integration_connection_circuit_state",
        ),
        sa.CheckConstraint(
            "timeout_seconds BETWEEN 1 AND 600",
            name="ck_integration_connection_timeout",
        ),
        sa.CheckConstraint(
            "retry_max_attempts BETWEEN 1 AND 20 "
            "AND retry_base_seconds BETWEEN 1 AND 86400",
            name="ck_integration_connection_retry",
        ),
        sa.CheckConstraint(
            "rate_limit_per_minute IS NULL OR rate_limit_per_minute > 0",
            name="ck_integration_connection_rate_limit",
        ),
        sa.CheckConstraint(
            "rate_limit_remaining IS NULL OR rate_limit_remaining >= 0",
            name="ck_integration_connection_rate_remaining",
        ),
        sa.CheckConstraint(
            "circuit_breaker_failure_threshold BETWEEN 1 AND 100 "
            "AND circuit_breaker_failure_count >= 0",
            name="ck_integration_connection_circuit_counts",
        ),
        sa.CheckConstraint(
            "user_id IS NULL OR workspace_id IS NOT NULL",
            name="ck_integration_connection_user_workspace",
        ),
        sa.CheckConstraint(
            "configuration_reference IS NULL "
            "OR configuration_reference NOT LIKE '%://%@%'",
            name="ck_integration_connection_config_ref",
        ),
        sa.CheckConstraint(
            "endpoint_url IS NULL OR (endpoint_url LIKE 'https://%' "
            "AND endpoint_url NOT LIKE '%://%@%' AND endpoint_url NOT LIKE '%?%' "
            "AND endpoint_url NOT LIKE '%#%')",
            name="ck_integration_connection_endpoint",
        ),
        sa.CheckConstraint(
            _SECRET_REFERENCE_CHECK.format(column="credential_reference"),
            name="ck_integration_connection_credential_ref",
        ),
        sa.CheckConstraint(
            _SECRET_REFERENCE_CHECK.format(column="webhook_secret_reference"),
            name="ck_integration_connection_webhook_ref",
        ),
        sa.CheckConstraint(
            "lower(settings_json) NOT LIKE '%\"password\"%' "
            "AND lower(settings_json) NOT LIKE '%\"api_key\"%' "
            "AND lower(settings_json) NOT LIKE '%\"apikey\"%' "
            "AND lower(settings_json) NOT LIKE '%\"client_secret\"%' "
            "AND lower(settings_json) NOT LIKE '%\"access_token\"%' "
            "AND lower(settings_json) NOT LIKE '%\"refresh_token\"%' "
            "AND lower(settings_json) NOT LIKE '%\"connection_string\"%' "
            "AND settings_json NOT LIKE '%://%@%'",
            name="ck_integration_connection_settings_nonsecret",
        ),
        sa.CheckConstraint(
            "(status = 'DISCONNECTED' AND disconnected_at IS NOT NULL AND enabled = false) "
            "OR (status <> 'DISCONNECTED' AND disconnected_at IS NULL "
            "AND disconnected_by_user_id IS NULL)",
            name="ck_integration_connection_disconnect",
        ),
        sa.CheckConstraint(
            "(circuit_breaker_state = 'CLOSED' AND circuit_breaker_opened_at IS NULL) "
            "OR (circuit_breaker_state IN ('OPEN', 'HALF_OPEN') "
            "AND circuit_breaker_opened_at IS NOT NULL)",
            name="ck_integration_connection_circuit_timing",
        ),
        sa.CheckConstraint(
            "health_status = 'UNKNOWN' OR health_checked_at IS NOT NULL",
            name="ck_integration_connection_health_timing",
        ),
        sa.CheckConstraint(
            "last_error_at IS NOT NULL OR (last_error_code IS NULL AND last_error_summary IS NULL)",
            name="ck_integration_connection_error_timing",
        ),
        sa.CheckConstraint(
            "lifecycle_version > 0",
            name="ck_integration_connection_version",
        ),
    )
    op.create_index(
        "ix_integration_connections_organization_id",
        "integration_connections",
        ["organization_id"],
    )
    op.create_index(
        "ix_integration_connections_workspace_id",
        "integration_connections",
        ["workspace_id"],
    )
    op.create_index(
        "ix_integration_connections_user_id",
        "integration_connections",
        ["user_id"],
    )
    op.create_index(
        "ix_integration_connections_provider_family",
        "integration_connections",
        ["provider_family"],
    )
    op.create_index(
        "ix_integration_connections_provider_code",
        "integration_connections",
        ["provider_code"],
    )
    op.create_index(
        "ix_integration_connection_provider_scope",
        "integration_connections",
        ["organization_id", "workspace_id", "provider_family", "provider_code"],
    )
    op.create_index(
        "ix_integration_connection_health_state",
        "integration_connections",
        ["status", "health_status", "circuit_breaker_state"],
    )

    op.create_table(
        "integration_sync_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("operation", sa.String(100), nullable=False),
        sa.Column("trigger_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(100), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("failure_code", sa.String(80), nullable=True),
        sa.Column("failure_summary", sa.String(500), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("requested_by_user_id", sa.String(36), nullable=True),
        sa.Column(
            "lifecycle_version", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["connection_id", "organization_id"],
            ["integration_connections.id", "integration_connections.organization_id"],
            name="fk_integration_sync_run_connection_org",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["companies.id"],
            name="fk_integration_sync_run_organization",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "organization_id"],
            ["accounts.id", "accounts.organization_id"],
            name="fk_integration_sync_run_workspace_org",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            name="fk_integration_sync_run_requested_by",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "connection_id",
            "workspace_id",
            "idempotency_key",
            name="uq_integration_sync_run_connection_idempotency",
        ),
        sa.UniqueConstraint(
            "id",
            "connection_id",
            "organization_id",
            "workspace_id",
            name="uq_integration_sync_run_id_connection_org_workspace",
        ),
        sa.CheckConstraint(
            "direction IN ('INBOUND', 'OUTBOUND')",
            name="ck_integration_sync_run_direction",
        ),
        sa.CheckConstraint(
            "trigger_type IN ('SCHEDULED', 'MANUAL', 'WEBHOOK', 'EVENT', 'RETRY', 'BACKFILL')",
            name="ck_integration_sync_run_trigger",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'PARTIAL', "
            "'RETRY_SCHEDULED', 'FAILED', 'DEAD_LETTERED', 'CANCELLED')",
            name="ck_integration_sync_run_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts BETWEEN 1 AND 20 "
            "AND attempt_count <= max_attempts",
            name="ck_integration_sync_run_attempts",
        ),
        sa.CheckConstraint(
            "length(payload_sha256) = 64 AND payload_sha256 = lower(payload_sha256)",
            name="ck_integration_sync_run_payload_hash",
        ),
        sa.CheckConstraint(
            "next_retry_at IS NULL OR status = 'RETRY_SCHEDULED'",
            name="ck_integration_sync_run_retry_state",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR status IN "
            "('SUCCEEDED', 'PARTIAL', 'FAILED', 'DEAD_LETTERED', 'CANCELLED')",
            name="ck_integration_sync_run_finished_state",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="ck_integration_sync_run_timing",
        ),
        sa.CheckConstraint(
            "(failure_code IS NULL AND failure_summary IS NULL) OR status IN "
            "('RETRY_SCHEDULED', 'FAILED', 'DEAD_LETTERED')",
            name="ck_integration_sync_run_failure_state",
        ),
        sa.CheckConstraint(
            "lifecycle_version > 0",
            name="ck_integration_sync_run_version",
        ),
    )
    for column in (
        "connection_id",
        "organization_id",
        "workspace_id",
        "correlation_id",
        "status",
    ):
        op.create_index(
            f"ix_integration_sync_runs_{column}",
            "integration_sync_runs",
            [column],
        )
    op.create_index(
        "ix_integration_sync_run_queue",
        "integration_sync_runs",
        ["status", "next_retry_at", "created_at"],
    )
    op.create_index(
        "ix_integration_sync_run_scope_time",
        "integration_sync_runs",
        ["organization_id", "workspace_id", "created_at"],
    )

    op.create_table(
        "integration_sync_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("operation", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=True),
        sa.Column("resource_id", sa.String(160), nullable=True),
        sa.Column("external_reference", sa.String(300), nullable=True),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("failure_code", sa.String(80), nullable=True),
        sa.Column("failure_summary", sa.String(500), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "lifecycle_version", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "connection_id", "organization_id", "workspace_id"],
            [
                "integration_sync_runs.id",
                "integration_sync_runs.connection_id",
                "integration_sync_runs.organization_id",
                "integration_sync_runs.workspace_id",
            ],
            name="fk_integration_sync_event_run_connection_org_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["companies.id"],
            name="fk_integration_sync_event_organization",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "organization_id"],
            ["accounts.id", "accounts.organization_id"],
            name="fk_integration_sync_event_workspace_org",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "connection_id",
            "workspace_id",
            "idempotency_key",
            name="uq_integration_sync_event_connection_idempotency",
        ),
        sa.CheckConstraint(
            "direction IN ('INBOUND', 'OUTBOUND')",
            name="ck_integration_sync_event_direction",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'SUCCEEDED', 'RETRY_SCHEDULED', "
            "'FAILED', 'DEAD_LETTERED', 'SKIPPED')",
            name="ck_integration_sync_event_status",
        ),
        sa.CheckConstraint(
            "(resource_type IS NULL AND resource_id IS NULL) "
            "OR (resource_type IS NOT NULL AND resource_id IS NOT NULL)",
            name="ck_integration_sync_event_resource_pair",
        ),
        sa.CheckConstraint(
            "external_reference IS NULL OR external_reference NOT LIKE '%://%'",
            name="ck_integration_sync_event_external_opaque",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts BETWEEN 1 AND 20 "
            "AND attempt_count <= max_attempts",
            name="ck_integration_sync_event_attempts",
        ),
        sa.CheckConstraint(
            "length(payload_sha256) = 64 AND payload_sha256 = lower(payload_sha256)",
            name="ck_integration_sync_event_payload_hash",
        ),
        sa.CheckConstraint(
            "next_retry_at IS NULL OR status = 'RETRY_SCHEDULED'",
            name="ck_integration_sync_event_retry_state",
        ),
        sa.CheckConstraint(
            "processed_at IS NULL OR status IN "
            "('SUCCEEDED', 'FAILED', 'DEAD_LETTERED', 'SKIPPED')",
            name="ck_integration_sync_event_processed_state",
        ),
        sa.CheckConstraint(
            "(failure_code IS NULL AND failure_summary IS NULL) OR status IN "
            "('RETRY_SCHEDULED', 'FAILED', 'DEAD_LETTERED')",
            name="ck_integration_sync_event_failure_state",
        ),
        sa.CheckConstraint(
            "lifecycle_version > 0",
            name="ck_integration_sync_event_version",
        ),
    )
    for column in (
        "run_id",
        "connection_id",
        "organization_id",
        "workspace_id",
        "status",
    ):
        op.create_index(
            f"ix_integration_sync_events_{column}",
            "integration_sync_events",
            [column],
        )
    op.create_index(
        "ix_integration_sync_event_queue",
        "integration_sync_events",
        ["status", "next_retry_at", "created_at"],
    )
    op.create_index(
        "ix_integration_sync_event_resource",
        "integration_sync_events",
        ["organization_id", "workspace_id", "resource_type", "resource_id"],
    )
    op.create_index(
        "ix_integration_sync_event_external",
        "integration_sync_events",
        ["connection_id", "external_reference"],
    )

    op.create_table(
        "feature_flag_overrides",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("flag_key", sa.String(120), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False, server_default="GEOVISION"),
        sa.Column("configuration_reference", sa.String(500), nullable=True),
        sa.Column("etag", sa.String(200), nullable=True),
        sa.Column("configuration_version", sa.String(120), nullable=True),
        sa.Column(
            "lifecycle_version", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(36), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["companies.id"],
            name="fk_feature_flag_override_organization",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "organization_id"],
            ["accounts.id", "accounts.organization_id"],
            name="fk_feature_flag_override_workspace_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["account_members.account_id", "account_members.user_id"],
            name="fk_feature_flag_override_workspace_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_feature_flag_override_created_by",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name="fk_feature_flag_override_updated_by",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "length(trim(flag_key)) > 0 AND flag_key = lower(flag_key)",
            name="ck_feature_flag_override_key",
        ),
        sa.CheckConstraint(
            "source IN ('GEOVISION', 'AZURE_APP_CONFIGURATION')",
            name="ck_feature_flag_override_source",
        ),
        sa.CheckConstraint(
            "configuration_reference IS NULL "
            "OR configuration_reference NOT LIKE '%://%@%'",
            name="ck_feature_flag_override_config_ref",
        ),
        sa.CheckConstraint(
            "source <> 'AZURE_APP_CONFIGURATION' OR configuration_reference IS NOT NULL",
            name="ck_feature_flag_override_azure_ref",
        ),
        sa.CheckConstraint(
            "lifecycle_version > 0",
            name="ck_feature_flag_override_version",
        ),
    )
    for column in ("organization_id", "workspace_id", "user_id"):
        op.create_index(
            f"ix_feature_flag_overrides_{column}",
            "feature_flag_overrides",
            [column],
        )
    op.create_index(
        "uq_feature_flag_override_workspace_flag",
        "feature_flag_overrides",
        ["organization_id", "workspace_id", "flag_key"],
        unique=True,
        sqlite_where=sa.text("user_id IS NULL"),
        postgresql_where=sa.text("user_id IS NULL"),
    )
    op.create_index(
        "uq_feature_flag_override_user_flag",
        "feature_flag_overrides",
        ["organization_id", "workspace_id", "user_id", "flag_key"],
        unique=True,
        sqlite_where=sa.text("user_id IS NOT NULL"),
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "ix_feature_flag_override_lookup",
        "feature_flag_overrides",
        ["workspace_id", "user_id", "flag_key", "enabled"],
    )


def downgrade() -> None:
    op.drop_table("feature_flag_overrides")
    op.drop_table("integration_sync_events")
    op.drop_table("integration_sync_runs")
    op.drop_table("integration_connections")

    with op.batch_alter_table("accounts") as batch:
        batch.drop_constraint("uq_accounts_id_organization", type_="unique")
