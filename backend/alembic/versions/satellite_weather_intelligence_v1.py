"""Add cached satellite/weather intelligence and recurring schedules.

Revision ID: satellite_weather_v1
Revises: processing_jobs_v1
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "satellite_weather_v1"
down_revision = "processing_jobs_v1"
branch_labels = None
depends_on = None


def _indexes(table: str, columns: tuple[str, ...]) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade() -> None:
    op.create_table(
        "intelligence_schedules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("provider_code", sa.String(length=80), nullable=False),
        sa.Column("cadence_minutes", sa.Integer(), nullable=False, server_default="10080"),
        sa.Column("lookback_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("options_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("next_run_at", sa.DateTime(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claimed_by", sa.String(length=100), nullable=True),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("lifecycle_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('SATELLITE', 'WEATHER')", name="ck_intelligence_schedule_kind"
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'PAUSED', 'DISABLED')",
            name="ck_intelligence_schedule_status",
        ),
        sa.CheckConstraint(
            "cadence_minutes > 0 AND lookback_days > 0 AND consecutive_failures >= 0",
            name="ck_intelligence_schedule_intervals",
        ),
        sa.CheckConstraint(
            "lifecycle_version > 0", name="ck_intelligence_schedule_version"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    _indexes(
        "intelligence_schedules",
        (
            "organization_id",
            "workspace_id",
            "asset_id",
            "kind",
            "provider_code",
            "status",
            "next_run_at",
        ),
    )
    op.create_index(
        "ix_intelligence_schedules_due",
        "intelligence_schedules",
        ["status", "next_run_at", "created_at"],
    )

    op.create_table(
        "intelligence_acquisitions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("schedule_id", sa.String(length=36), nullable=True),
        sa.Column("acquisition_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("provider_code", sa.String(length=80), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("request_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("result_summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("dataset_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="REQUESTED"),
        sa.Column("cache_expires_at", sa.DateTime(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("claimed_by", sa.String(length=100), nullable=True),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("lifecycle_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('SATELLITE', 'WEATHER')", name="ck_intelligence_acquisition_kind"
        ),
        sa.CheckConstraint(
            "status IN ('REQUESTED', 'RUNNING', 'RETRY_WAIT', 'COMPLETED', 'FAILED')",
            name="ck_intelligence_acquisition_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0",
            name="ck_intelligence_acquisition_attempts",
        ),
        sa.CheckConstraint(
            "lifecycle_version > 0", name="ck_intelligence_acquisition_version"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["schedule_id"], ["intelligence_schedules.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["acquisition_id"], ["acquisitions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    _indexes(
        "intelligence_acquisitions",
        (
            "organization_id",
            "workspace_id",
            "asset_id",
            "schedule_id",
            "acquisition_id",
            "kind",
            "provider_code",
            "request_fingerprint",
            "status",
            "cache_expires_at",
            "next_attempt_at",
        ),
    )
    op.create_index(
        "ix_intelligence_acquisitions_cache",
        "intelligence_acquisitions",
        [
            "organization_id",
            "asset_id",
            "kind",
            "provider_code",
            "request_fingerprint",
            "status",
            "cache_expires_at",
        ],
    )
    op.create_index(
        "ix_intelligence_acquisitions_due",
        "intelligence_acquisitions",
        ["status", "next_attempt_at", "created_at"],
    )

    op.create_table(
        "satellite_scenes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("intelligence_acquisition_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("provider_code", sa.String(length=80), nullable=False),
        sa.Column("provider_reference", sa.String(length=240), nullable=False),
        sa.Column("collection", sa.String(length=120), nullable=False),
        sa.Column("acquired_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("cloud_cover_percent", sa.Float(), nullable=True),
        sa.Column("resolution_meters", sa.Float(), nullable=True),
        sa.Column("crs", sa.String(length=100), nullable=True),
        sa.Column("bands_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("bbox_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("coverage_geojson", sa.Text(), nullable=True),
        sa.Column("assets_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("provenance_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("source_link", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "cloud_cover_percent IS NULL OR "
            "(cloud_cover_percent >= 0 AND cloud_cover_percent <= 100)",
            name="ck_satellite_scene_cloud_cover",
        ),
        sa.CheckConstraint(
            "resolution_meters IS NULL OR resolution_meters > 0",
            name="ck_satellite_scene_resolution",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["intelligence_acquisition_id"],
            ["intelligence_acquisitions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id"),
        sa.UniqueConstraint(
            "asset_id",
            "provider_code",
            "provider_reference",
            name="uq_satellite_scene_asset_source",
        ),
    )
    _indexes(
        "satellite_scenes",
        (
            "organization_id",
            "asset_id",
            "intelligence_acquisition_id",
            "provider_code",
            "collection",
            "acquired_at",
        ),
    )
    op.create_index(
        "ix_satellite_scenes_asset_time",
        "satellite_scenes",
        ["asset_id", "acquired_at"],
    )

    op.create_table(
        "weather_observations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("intelligence_acquisition_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("provider_code", sa.String(length=80), nullable=False),
        sa.Column("source_reference", sa.String(length=160), nullable=False),
        sa.Column("source_name", sa.String(length=240), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("metric", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=40), nullable=False),
        sa.Column("quality", sa.String(length=30), nullable=False, server_default="observed"),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("distance_km", sa.Float(), nullable=True),
        sa.Column("provenance_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="ck_weather_observation_latitude",
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="ck_weather_observation_longitude",
        ),
        sa.CheckConstraint(
            "distance_km IS NULL OR distance_km >= 0",
            name="ck_weather_observation_distance",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["intelligence_acquisition_id"],
            ["intelligence_acquisitions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "asset_id",
            "provider_code",
            "source_reference",
            "observed_at",
            "metric",
            name="uq_weather_observation_asset_source_time_metric",
        ),
    )
    _indexes(
        "weather_observations",
        (
            "organization_id",
            "asset_id",
            "intelligence_acquisition_id",
            "dataset_id",
            "provider_code",
            "source_reference",
            "observed_at",
            "metric",
        ),
    )
    op.create_index(
        "ix_weather_observations_asset_metric_time",
        "weather_observations",
        ["asset_id", "metric", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_weather_observations_asset_metric_time", table_name="weather_observations"
    )
    for column in reversed(
        (
            "organization_id",
            "asset_id",
            "intelligence_acquisition_id",
            "dataset_id",
            "provider_code",
            "source_reference",
            "observed_at",
            "metric",
        )
    ):
        op.drop_index(f"ix_weather_observations_{column}", table_name="weather_observations")
    op.drop_table("weather_observations")

    op.drop_index("ix_satellite_scenes_asset_time", table_name="satellite_scenes")
    for column in reversed(
        (
            "organization_id",
            "asset_id",
            "intelligence_acquisition_id",
            "provider_code",
            "collection",
            "acquired_at",
        )
    ):
        op.drop_index(f"ix_satellite_scenes_{column}", table_name="satellite_scenes")
    op.drop_table("satellite_scenes")

    op.drop_index(
        "ix_intelligence_acquisitions_due", table_name="intelligence_acquisitions"
    )
    op.drop_index(
        "ix_intelligence_acquisitions_cache", table_name="intelligence_acquisitions"
    )
    for column in reversed(
        (
            "organization_id",
            "workspace_id",
            "asset_id",
            "schedule_id",
            "acquisition_id",
            "kind",
            "provider_code",
            "request_fingerprint",
            "status",
            "cache_expires_at",
            "next_attempt_at",
        )
    ):
        op.drop_index(
            f"ix_intelligence_acquisitions_{column}",
            table_name="intelligence_acquisitions",
        )
    op.drop_table("intelligence_acquisitions")

    op.drop_index("ix_intelligence_schedules_due", table_name="intelligence_schedules")
    for column in reversed(
        (
            "organization_id",
            "workspace_id",
            "asset_id",
            "kind",
            "provider_code",
            "status",
            "next_run_at",
        )
    ):
        op.drop_index(
            f"ix_intelligence_schedules_{column}", table_name="intelligence_schedules"
        )
    op.drop_table("intelligence_schedules")
