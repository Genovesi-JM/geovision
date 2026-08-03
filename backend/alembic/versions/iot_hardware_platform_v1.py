"""hardware-ready IoT platform

Revision ID: iot_hardware_platform_v1
Revises: drone_automation_v1
"""

from alembic import op
import sqlalchemy as sa

revision = "iot_hardware_platform_v1"
down_revision = "drone_automation_v1"
branch_labels = None
depends_on = None


def upgrade():
    # The ORM has long exposed ``Site.country`` but the enterprise schema did
    # not create it.  IoT provisioning reads sites through that model, so make
    # the migrated schema match before creating hardware tables.
    op.add_column(
        "sites",
        sa.Column("country", sa.String(100), nullable=False, server_default="Angola"),
    )
    op.create_table("iot_devices",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("public_id", sa.String(80), nullable=False),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", sa.String(36), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", sa.String(36)), sa.Column("gateway_id", sa.String(36)),
        sa.Column("name", sa.String(160), nullable=False), sa.Column("device_type", sa.String(60), nullable=False),
        sa.Column("transport", sa.String(30), nullable=False), sa.Column("firmware_version", sa.String(80)),
        sa.Column("hardware_model", sa.String(120)), sa.Column("status", sa.String(30), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False), sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("capabilities_json", sa.Text(), nullable=False), sa.Column("configuration_json", sa.Text(), nullable=False),
        sa.Column("allow_remote_control", sa.Boolean(), nullable=False), sa.Column("last_seen_at", sa.DateTime()),
        sa.Column("last_ip", sa.String(45)), sa.Column("created_by", sa.String(36)),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("public_id"))
    for name, cols in (("ix_iot_devices_company_id", ["company_id"]), ("ix_iot_devices_site_id", ["site_id"]), ("ix_iot_devices_status", ["status"]), ("ix_iot_devices_public_id", ["public_id"])):
        op.create_index(name, "iot_devices", cols)

    op.create_table("iot_assets",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("site_id", sa.String(36), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False), sa.Column("asset_type", sa.String(80), nullable=False),
        sa.Column("external_reference", sa.String(120)), sa.Column("latitude", sa.Float()), sa.Column("longitude", sa.Float()),
        sa.Column("metadata_json", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_iot_assets_company_id", "iot_assets", ["company_id"]); op.create_index("ix_iot_assets_site_id", "iot_assets", ["site_id"])

    op.create_table("iot_gateways",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("site_id", sa.String(36), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("iot_devices.id", ondelete="SET NULL"), unique=True),
        sa.Column("name", sa.String(160), nullable=False), sa.Column("gateway_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False), sa.Column("configuration_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))

    op.create_table("sensor_channels",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("device_id", sa.String(36), sa.ForeignKey("iot_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("iot_assets.id", ondelete="SET NULL")),
        sa.Column("key", sa.String(100), nullable=False), sa.Column("label", sa.String(160), nullable=False),
        sa.Column("measurement_type", sa.String(80), nullable=False), sa.Column("unit", sa.String(30)),
        sa.Column("data_type", sa.String(20), nullable=False), sa.Column("minimum", sa.Float()), sa.Column("maximum", sa.Float()),
        sa.Column("precision", sa.Integer(), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.UniqueConstraint("device_id", "key", name="uq_sensor_channel_device_key"))
    op.create_index("ix_sensor_channels_device_id", "sensor_channels", ["device_id"])

    op.create_table("device_credentials",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("device_id", sa.String(36), sa.ForeignKey("iot_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False), sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime()), sa.Column("revoked_at", sa.DateTime()))
    op.create_index("ix_device_credentials_device_id", "device_credentials", ["device_id"])

    op.create_table("device_provisioning_tokens",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("device_id", sa.String(36), sa.ForeignKey("iot_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True), sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime()), sa.Column("created_by", sa.String(36), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))

    op.create_table("calibration_records",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("sensor_channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("offset", sa.Float(), nullable=False), sa.Column("scale", sa.Float(), nullable=False),
        sa.Column("reference_value", sa.Float()), sa.Column("measured_value", sa.Float()), sa.Column("notes", sa.Text()),
        sa.Column("calibrated_by", sa.String(36), nullable=False), sa.Column("calibrated_at", sa.DateTime(), nullable=False))

    op.create_table("commissioning_records",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("iot_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("technician_id", sa.String(36), nullable=False), sa.Column("checklist_json", sa.Text(), nullable=False),
        sa.Column("result", sa.String(30), nullable=False), sa.Column("notes", sa.Text()), sa.Column("commissioned_at", sa.DateTime(), nullable=False))

    op.create_table("telemetry_readings",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("device_id", sa.String(36), sa.ForeignKey("iot_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.String(36), nullable=False), sa.Column("site_id", sa.String(36), nullable=False),
        sa.Column("message_id", sa.String(100), nullable=False), sa.Column("channel", sa.String(100), nullable=False),
        sa.Column("numeric_value", sa.Float()), sa.Column("text_value", sa.Text()), sa.Column("boolean_value", sa.Boolean()),
        sa.Column("unit", sa.String(30)), sa.Column("quality", sa.String(20), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False), sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False), sa.UniqueConstraint("device_id", "message_id", "channel", name="uq_telemetry_message_channel"))
    op.create_index("ix_telemetry_device_channel_time", "telemetry_readings", ["device_id", "channel", "recorded_at"])
    op.create_index("ix_telemetry_company_time", "telemetry_readings", ["company_id", "recorded_at"])

    op.create_table("telemetry_aggregates",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("device_id", sa.String(36), sa.ForeignKey("iot_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.String(36), nullable=False), sa.Column("site_id", sa.String(36), nullable=False),
        sa.Column("channel", sa.String(100), nullable=False), sa.Column("unit", sa.String(30)),
        sa.Column("bucket_start", sa.DateTime(), nullable=False), sa.Column("bucket_seconds", sa.Integer(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False), sa.Column("minimum", sa.Float(), nullable=False),
        sa.Column("maximum", sa.Float(), nullable=False), sa.Column("average", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("device_id", "channel", "bucket_start", "bucket_seconds", name="uq_telemetry_aggregate_bucket"))
    op.create_index("ix_telemetry_aggregate_device_time", "telemetry_aggregates", ["device_id", "channel", "bucket_start"])

    op.create_table("iot_alert_rules",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("iot_devices.id", ondelete="CASCADE")), sa.Column("site_id", sa.String(36)),
        sa.Column("name", sa.String(160), nullable=False), sa.Column("channel", sa.String(100), nullable=False),
        sa.Column("operator", sa.String(10), nullable=False), sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False), sa.Column("cooldown_seconds", sa.Integer(), nullable=False),
        sa.Column("sustained_seconds", sa.Integer(), nullable=False), sa.Column("notification_channels_json", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))

    op.create_table("iot_alerts",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("iot_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", sa.String(36), sa.ForeignKey("iot_alert_rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(100), nullable=False), sa.Column("value", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False), sa.Column("message", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime()), sa.Column("acknowledged_by", sa.String(36)),
        sa.Column("assigned_at", sa.DateTime()), sa.Column("assigned_to", sa.String(36)),
        sa.Column("resolved_at", sa.DateTime()), sa.Column("closed_at", sa.DateTime()))

    op.create_table("iot_commands",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("iot_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by", sa.String(36), nullable=False), sa.Column("correlation_id", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False), sa.Column("arguments_json", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False), sa.Column("fail_safe_state", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False), sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("delivered_at", sa.DateTime()), sa.Column("acknowledged_at", sa.DateTime()),
        sa.Column("result_json", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))

    op.create_table("iot_message_nonces",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("device_id", sa.String(36), sa.ForeignKey("iot_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nonce", sa.String(100), nullable=False), sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("device_id", "nonce", name="uq_iot_device_nonce"))


def downgrade():
    for table in ("iot_message_nonces", "iot_commands", "iot_alerts", "iot_alert_rules", "telemetry_aggregates", "telemetry_readings", "commissioning_records", "calibration_records", "device_provisioning_tokens", "device_credentials", "sensor_channels", "iot_gateways", "iot_assets", "iot_devices"):
        op.drop_table(table)
    op.drop_column("sites", "country")
