"""Add first-class IoT assignments and durable edge telemetry receipts.

Revision ID: iot_edge_contract_v1
Revises: satellite_weather_v1
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from alembic import op
import sqlalchemy as sa


revision = "iot_edge_contract_v1"
down_revision = "satellite_weather_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("iot_devices") as batch:
        batch.add_column(sa.Column("core_asset_id", sa.String(36), nullable=True))
        batch.add_column(
            sa.Column(
                "provider_code",
                sa.String(80),
                nullable=False,
                server_default="geovision",
            )
        )
        batch.add_column(sa.Column("provider_device_id", sa.String(160), nullable=True))
        batch.add_column(
            sa.Column(
                "protocol_version",
                sa.String(40),
                nullable=False,
                server_default="geovision.telemetry.v1",
            )
        )
        batch.add_column(
            sa.Column(
                "connectivity_status",
                sa.String(20),
                nullable=False,
                server_default="unknown",
            )
        )
        batch.add_column(sa.Column("battery_percent", sa.Float(), nullable=True))
        batch.add_column(
            sa.Column(
                "health_status", sa.String(20), nullable=False, server_default="unknown"
            )
        )
        batch.add_column(sa.Column("last_latitude", sa.Float(), nullable=True))
        batch.add_column(sa.Column("last_longitude", sa.Float(), nullable=True))
        batch.add_column(sa.Column("last_stream_id", sa.String(100), nullable=True))
        batch.add_column(sa.Column("last_sequence", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_iot_devices_core_asset_id_assets",
            "assets",
            ["core_asset_id"],
            ["id"],
            ondelete="SET NULL",
        )

    for column in (
        "core_asset_id",
        "provider_code",
        "connectivity_status",
        "health_status",
    ):
        op.create_index(f"ix_iot_devices_{column}", "iot_devices", [column])
    op.create_index(
        "uq_iot_devices_provider_identity",
        "iot_devices",
        ["provider_code", "provider_device_id"],
        unique=True,
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE iot_devices
               SET provider_device_id = public_id,
                   connectivity_status = CASE
                       WHEN status = 'online' THEN 'online'
                       WHEN status = 'offline' THEN 'offline'
                       ELSE 'unknown'
                   END,
                   core_asset_id = COALESCE(
                       (
                           SELECT assets.id
                             FROM assets
                            WHERE assets.legacy_source = 'iot_asset'
                              AND assets.legacy_source_id = iot_devices.asset_id
                            LIMIT 1
                       ),
                       (
                           SELECT assets.id
                             FROM assets
                            WHERE assets.legacy_source = 'site'
                              AND assets.legacy_source_id = iot_devices.site_id
                            LIMIT 1
                       )
                   )
            """
        )
    )

    op.create_table(
        "iot_device_assignments",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column("legacy_iot_asset_id", sa.String(36), nullable=True),
        sa.Column("gateway_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("assigned_by", sa.String(36), nullable=True),
        sa.Column("assigned_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'ended')", name="ck_iot_device_assignment_status"
        ),
        sa.CheckConstraint(
            "(status = 'active' AND ended_at IS NULL) OR "
            "(status = 'ended' AND ended_at IS NOT NULL)",
            name="ck_iot_device_assignment_end_state",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["iot_devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["legacy_iot_asset_id"], ["iot_assets.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["gateway_id"], ["iot_gateways.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "company_id",
        "device_id",
        "asset_id",
        "legacy_iot_asset_id",
        "gateway_id",
        "status",
    ):
        op.create_index(
            f"ix_iot_device_assignments_{column}",
            "iot_device_assignments",
            [column],
        )
    op.create_index(
        "ix_iot_device_assignments_device_time",
        "iot_device_assignments",
        ["device_id", "assigned_at"],
    )
    op.create_index(
        "uq_iot_device_assignments_active",
        "iot_device_assignments",
        ["device_id"],
        unique=True,
        sqlite_where=sa.text("status = 'active'"),
        postgresql_where=sa.text("status = 'active'"),
    )

    rows = bind.execute(
        sa.text(
            """
            SELECT d.id, d.company_id, d.core_asset_id, d.asset_id, d.created_at,
                   CASE WHEN a.id IS NULL THEN NULL ELSE d.asset_id END AS valid_legacy_id
              FROM iot_devices AS d
              LEFT JOIN iot_assets AS a ON a.id = d.asset_id
             WHERE d.core_asset_id IS NOT NULL
            """
        )
    ).mappings()
    insert_assignment = sa.text(
        """
        INSERT INTO iot_device_assignments
            (id, company_id, device_id, asset_id, legacy_iot_asset_id, gateway_id,
             status, reason, assigned_by, assigned_at, ended_at, created_at)
        VALUES
            (:id, :company_id, :device_id, :asset_id, :legacy_iot_asset_id, NULL,
             'active', 'migration backfill', NULL, :assigned_at, NULL, :created_at)
        """
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for row in rows:
        assigned_at = row["created_at"] or now
        bind.execute(
            insert_assignment,
            {
                "id": str(uuid.uuid4()),
                "company_id": row["company_id"],
                "device_id": row["id"],
                "asset_id": row["core_asset_id"],
                "legacy_iot_asset_id": row["valid_legacy_id"],
                "assigned_at": assigned_at,
                "created_at": assigned_at,
            },
        )

    op.create_table(
        "iot_telemetry_receipts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("site_id", sa.String(36), nullable=False),
        sa.Column("core_asset_id", sa.String(36), nullable=True),
        sa.Column("message_id", sa.String(100), nullable=False),
        sa.Column("provider_code", sa.String(80), nullable=False),
        sa.Column("provider_message_id", sa.String(200), nullable=True),
        sa.Column("protocol_version", sa.String(40), nullable=False),
        sa.Column("firmware_version", sa.String(80), nullable=True),
        sa.Column("stream_id", sa.String(100), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("out_of_order", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "replayed_from_edge", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("queued_at", sa.DateTime(), nullable=True),
        sa.Column("measurement_count", sa.Integer(), nullable=False),
        sa.Column("context_json", sa.Text(), nullable=False, server_default="{}"),
        sa.CheckConstraint(
            "measurement_count > 0", name="ck_iot_telemetry_receipt_measurements"
        ),
        sa.CheckConstraint(
            "(stream_id IS NULL AND sequence IS NULL) OR "
            "(stream_id IS NOT NULL AND sequence IS NOT NULL AND sequence >= 0)",
            name="ck_iot_telemetry_receipt_sequence",
        ),
        sa.CheckConstraint(
            "NOT replayed_from_edge OR queued_at IS NOT NULL",
            name="ck_iot_telemetry_receipt_replay_queue",
        ),
        sa.ForeignKeyConstraint(["device_id"], ["iot_devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["core_asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "message_id", name="uq_iot_receipt_device_message"),
        sa.UniqueConstraint(
            "device_id",
            "stream_id",
            "sequence",
            name="uq_iot_receipt_device_stream_sequence",
        ),
        sa.UniqueConstraint(
            "provider_code",
            "provider_message_id",
            name="uq_iot_receipt_provider_message",
        ),
    )
    for column in (
        "device_id",
        "company_id",
        "site_id",
        "core_asset_id",
        "provider_code",
        "recorded_at",
        "received_at",
    ):
        op.create_index(
            f"ix_iot_telemetry_receipts_{column}",
            "iot_telemetry_receipts",
            [column],
        )
    op.create_index(
        "ix_iot_receipts_device_recorded",
        "iot_telemetry_receipts",
        ["device_id", "recorded_at"],
    )
    op.create_index(
        "ix_iot_receipts_asset_recorded",
        "iot_telemetry_receipts",
        ["core_asset_id", "recorded_at"],
    )

    with op.batch_alter_table("telemetry_readings") as batch:
        batch.add_column(sa.Column("receipt_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("core_asset_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("sequence", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("protocol_version", sa.String(40), nullable=True))
        batch.add_column(sa.Column("source", sa.String(40), nullable=True))
        batch.create_foreign_key(
            "fk_telemetry_readings_receipt_id",
            "iot_telemetry_receipts",
            ["receipt_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_telemetry_readings_core_asset_id",
            "assets",
            ["core_asset_id"],
            ["id"],
            ondelete="SET NULL",
        )
    for column in ("receipt_id", "core_asset_id", "source"):
        op.create_index(f"ix_telemetry_readings_{column}", "telemetry_readings", [column])
    bind.execute(
        sa.text(
            """
            UPDATE telemetry_readings
               SET core_asset_id = (
                       SELECT iot_devices.core_asset_id
                         FROM iot_devices
                        WHERE iot_devices.id = telemetry_readings.device_id
                   ),
                   protocol_version = 'geovision.telemetry.v1',
                   source = 'legacy'
            """
        )
    )


def downgrade() -> None:
    for column in ("source", "core_asset_id", "receipt_id"):
        op.drop_index(f"ix_telemetry_readings_{column}", table_name="telemetry_readings")
    with op.batch_alter_table("telemetry_readings") as batch:
        batch.drop_constraint("fk_telemetry_readings_core_asset_id", type_="foreignkey")
        batch.drop_constraint("fk_telemetry_readings_receipt_id", type_="foreignkey")
        for column in (
            "source",
            "protocol_version",
            "sequence",
            "core_asset_id",
            "receipt_id",
        ):
            batch.drop_column(column)

    op.drop_table("iot_telemetry_receipts")
    op.drop_table("iot_device_assignments")

    op.drop_index("uq_iot_devices_provider_identity", table_name="iot_devices")
    for column in (
        "health_status",
        "connectivity_status",
        "provider_code",
        "core_asset_id",
    ):
        op.drop_index(f"ix_iot_devices_{column}", table_name="iot_devices")
    with op.batch_alter_table("iot_devices") as batch:
        batch.drop_constraint("fk_iot_devices_core_asset_id_assets", type_="foreignkey")
        for column in (
            "last_sequence",
            "last_stream_id",
            "last_longitude",
            "last_latitude",
            "health_status",
            "battery_percent",
            "connectivity_status",
            "protocol_version",
            "provider_device_id",
            "provider_code",
            "core_asset_id",
        ):
            batch.drop_column(column)
