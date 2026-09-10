"""Make datasets asset-centric and object-storage-provider neutral.

Revision ID: datasets_storage_v2
Revises: acquisitions_v1
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "datasets_storage_v2"
down_revision = "acquisitions_v1"
branch_labels = None
depends_on = None


def _add_dataset_columns() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {
        column["name"]
        for column in inspector.get_columns("datasets")
    }
    site_foreign_key = next(
        (
            foreign_key
            for foreign_key in inspector.get_foreign_keys("datasets")
            if foreign_key.get("constrained_columns") == ["site_id"]
        ),
        None,
    )
    columns = (
        sa.Column("company_id", sa.String(length=36), nullable=True),
        sa.Column("source_tool", sa.String(length=50), nullable=True),
        sa.Column("sector", sa.String(length=50), nullable=True),
        sa.Column("capture_date", sa.DateTime(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True, server_default="{}"),
        sa.Column(
            "total_size_bytes", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("asset_id", sa.String(length=36), nullable=True),
        sa.Column("mission_id", sa.String(length=36), nullable=True),
        sa.Column(
            "dataset_type",
            sa.String(length=80),
            nullable=False,
            server_default="OTHER",
        ),
        sa.Column("provider_code", sa.String(length=80), nullable=True),
        sa.Column("source_reference", sa.String(length=240), nullable=True),
        sa.Column(
            "storage_provider",
            sa.String(length=40),
            nullable=False,
            server_default="legacy_unknown",
        ),
        sa.Column("object_prefix", sa.Text(), nullable=True),
        sa.Column("crs", sa.String(length=100), nullable=True),
        sa.Column("resolution", sa.Float(), nullable=True),
        sa.Column("resolution_unit", sa.String(length=30), nullable=True),
        sa.Column(
            "processing_level",
            sa.String(length=30),
            nullable=False,
            server_default="RAW",
        ),
        sa.Column(
            "quality_status",
            sa.String(length=30),
            nullable=False,
            server_default="UNREVIEWED",
        ),
        sa.Column(
            "provenance_json", sa.Text(), nullable=False, server_default="{}"
        ),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column(
            "lifecycle_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    naming_convention = {
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
    }
    with op.batch_alter_table(
        "datasets", naming_convention=naming_convention
    ) as batch:
        for column in columns:
            if column.name not in existing:
                batch.add_column(column)
        if site_foreign_key is not None:
            batch.drop_constraint(
                site_foreign_key.get("name") or "fk_datasets_site_id_sites",
                type_="foreignkey",
            )
        batch.create_foreign_key(
            "fk_datasets_site_id",
            "sites",
            ["site_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.alter_column(
            "site_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )


def _add_file_columns() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {
        column["name"]
        for column in inspector.get_columns("dataset_files")
    }
    dataset_foreign_key = next(
        (
            foreign_key
            for foreign_key in inspector.get_foreign_keys("dataset_files")
            if foreign_key.get("constrained_columns") == ["dataset_id"]
        ),
        None,
    )
    naming_convention = {
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
    }
    with op.batch_alter_table(
        "dataset_files", naming_convention=naming_convention
    ) as batch:
        if dataset_foreign_key is not None:
            batch.drop_constraint(
                dataset_foreign_key.get("name")
                or "fk_dataset_files_dataset_id_datasets",
                type_="foreignkey",
            )
        batch.create_foreign_key(
            "fk_dataset_files_dataset_id",
            "datasets",
            ["dataset_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        columns = (
            sa.Column(
                "storage_provider",
                sa.String(length=40),
                nullable=False,
                server_default="legacy_unknown",
            ),
            sa.Column("storage_uri", sa.Text(), nullable=True),
            sa.Column(
                "object_area",
                sa.String(length=20),
                nullable=False,
                server_default="raw",
            ),
            sa.Column("md5_hash", sa.String(length=32), nullable=True),
            sa.Column("sha256_hash", sa.String(length=64), nullable=True),
            sa.Column("upload_expires_at", sa.DateTime(), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column(
                "lifecycle_version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
        )
        for column in columns:
            if column.name not in existing:
                batch.add_column(column)


def _backfill() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE datasets
            SET company_id = COALESCE(
                    company_id,
                    (SELECT s.company_id FROM sites s WHERE s.id = datasets.site_id)
                ),
                source_tool = COALESCE(source_tool, LOWER(source), 'manual'),
                sector = COALESCE(
                    sector,
                    (SELECT s.sector FROM sites s WHERE s.id = datasets.site_id)
                ),
                capture_date = COALESCE(capture_date, collection_date),
                metadata_json = CASE
                    WHEN metadata_json IS NULL OR metadata_json = '{}'
                    THEN COALESCE(extra_data, '{}')
                    ELSE metadata_json
                END,
                total_size_bytes = CASE
                    WHEN total_size_bytes IS NULL OR total_size_bytes = 0
                    THEN CAST(COALESCE(storage_size_mb, 0) * 1048576 AS INTEGER)
                    ELSE total_size_bytes
                END,
                processed_at = COALESCE(processed_at, processing_date),
                asset_id = (
                    SELECT a.id
                    FROM assets a
                    WHERE a.legacy_source = 'site'
                      AND a.legacy_source_id = datasets.site_id
                    ORDER BY a.created_at, a.id
                    LIMIT 1
                ),
                workspace_id = (
                    SELECT a.workspace_id
                    FROM assets a
                    WHERE a.legacy_source = 'site'
                      AND a.legacy_source_id = datasets.site_id
                    ORDER BY a.created_at, a.id
                    LIMIT 1
                )
            WHERE site_id IS NOT NULL
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE datasets
            SET dataset_type = CASE LOWER(COALESCE(data_type, ''))
                    WHEN 'rgb_images' THEN 'RGB_IMAGES'
                    WHEN 'drone_imagery' THEN 'RGB_IMAGES'
                    WHEN 'multispectral_images' THEN 'MULTISPECTRAL_IMAGES'
                    WHEN 'thermal_images' THEN 'THERMAL_IMAGES'
                    WHEN 'orthomosaic' THEN 'ORTHOMOSAIC'
                    WHEN 'dsm' THEN 'DSM'
                    WHEN 'dtm' THEN 'DTM'
                    WHEN 'point_cloud' THEN 'POINT_CLOUD'
                    WHEN 'pointcloud' THEN 'POINT_CLOUD'
                    WHEN 'mesh_3d' THEN 'MESH_3D'
                    WHEN 'ndvi' THEN 'NDVI'
                    WHEN 'ndre' THEN 'NDRE'
                    WHEN 'gndvi' THEN 'GNDVI'
                    WHEN 'satellite_image' THEN 'SATELLITE_IMAGE'
                    WHEN 'weather_data' THEN 'WEATHER_DATA'
                    WHEN 'telemetry' THEN 'TELEMETRY'
                    WHEN 'ais_data' THEN 'AIS_DATA'
                    WHEN 'bim_model' THEN 'BIM_MODEL'
                    ELSE 'OTHER'
                END,
                provider_code = LOWER(COALESCE(source_tool, source)),
                source_reference = source,
                object_prefix = storage_path,
                storage_provider = CASE
                    WHEN storage_path LIKE '/%' THEN 'local'
                    WHEN storage_path IS NOT NULL THEN 's3'
                    ELSE 'legacy_unknown'
                END,
                status = CASE LOWER(COALESCE(status, 'pending'))
                    WHEN 'pending' THEN 'uploading'
                    WHEN 'complete' THEN 'ready'
                    WHEN 'completed' THEN 'ready'
                    WHEN 'uploaded' THEN 'processing'
                    WHEN 'uploading' THEN 'uploading'
                    WHEN 'processing' THEN 'processing'
                    WHEN 'ready' THEN 'ready'
                    WHEN 'error' THEN 'error'
                    ELSE 'error'
                END
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE dataset_files
            SET storage_provider = CASE
                    WHEN storage_key LIKE '/%' THEN 'local'
                    WHEN storage_key IS NOT NULL THEN 's3'
                    ELSE 'legacy_unknown'
                END,
                storage_uri = CASE
                    WHEN storage_key LIKE '/%' THEN 'local://' || storage_key
                    WHEN storage_key IS NOT NULL THEN 's3://' || storage_key
                    ELSE NULL
                END,
                status = CASE
                    WHEN storage_key IS NOT NULL THEN 'uploaded'
                    ELSE 'pending_upload'
                END,
                confirmed_at = CASE
                    WHEN storage_key IS NOT NULL THEN created_at
                    ELSE NULL
                END
            """
        )
    )


def _add_constraints_and_indexes() -> None:
    inspector = sa.inspect(op.get_bind())
    company_foreign_key = next(
        (
            foreign_key
            for foreign_key in inspector.get_foreign_keys("datasets")
            if foreign_key.get("constrained_columns") == ["company_id"]
        ),
        None,
    )
    naming_convention = {
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
    }
    with op.batch_alter_table(
        "datasets", naming_convention=naming_convention
    ) as batch:
        batch.alter_column(
            "company_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
        batch.alter_column(
            "status",
            existing_type=sa.String(length=20),
            existing_nullable=False,
            server_default=sa.text("'uploading'"),
        )
        if company_foreign_key is not None:
            batch.drop_constraint(
                company_foreign_key.get("name") or "fk_datasets_company_id_companies",
                type_="foreignkey",
            )
        batch.create_foreign_key(
            "fk_datasets_company_id",
            "companies",
            ["company_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_datasets_workspace_id",
            "accounts",
            ["workspace_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_datasets_asset_id",
            "assets",
            ["asset_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_datasets_mission_id",
            "acquisitions",
            ["mission_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_datasets_created_by_user_id",
            "users",
            ["created_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_check_constraint(
            "ck_dataset_resolution", "resolution IS NULL OR resolution > 0"
        )
        batch.create_check_constraint("ck_dataset_file_count", "file_count >= 0")
        batch.create_check_constraint(
            "ck_dataset_total_size", "total_size_bytes >= 0"
        )
        batch.create_check_constraint("ck_dataset_version", "lifecycle_version > 0")
    for column in (
        "workspace_id",
        "asset_id",
        "mission_id",
        "dataset_type",
        "provider_code",
        "processing_level",
        "quality_status",
    ):
        op.create_index(f"ix_datasets_{column}", "datasets", [column], unique=False)
    op.create_index(
        "ix_datasets_asset_capture",
        "datasets",
        ["asset_id", "capture_date"],
        unique=False,
    )
    with op.batch_alter_table("dataset_files") as batch:
        batch.alter_column(
            "status",
            existing_type=sa.String(length=30),
            existing_nullable=False,
            server_default=sa.text("'pending_upload'"),
        )
        batch.create_check_constraint("ck_dataset_file_size", "file_size >= 0")
        batch.create_check_constraint(
            "ck_dataset_file_version", "lifecycle_version > 0"
        )


def upgrade() -> None:
    _add_dataset_columns()
    _add_file_columns()
    _backfill()
    _add_constraints_and_indexes()


def downgrade() -> None:
    op.execute(
        sa.text("UPDATE datasets SET status = 'error' WHERE status = 'archived'")
    )
    op.execute(
        sa.text(
            """
            UPDATE dataset_files
            SET status = 'pending'
            WHERE status IN ('pending_upload', 'rejected', 'deleted')
            """
        )
    )
    with op.batch_alter_table("dataset_files") as batch:
        batch.alter_column(
            "status",
            existing_type=sa.String(length=30),
            existing_nullable=False,
            server_default=sa.text("'pending'"),
        )
        batch.drop_constraint("ck_dataset_file_version", type_="check")
        batch.drop_constraint("ck_dataset_file_size", type_="check")
        for column in (
            "lifecycle_version",
            "deleted_at",
            "confirmed_at",
            "upload_expires_at",
            "sha256_hash",
            "md5_hash",
            "object_area",
            "storage_uri",
            "storage_provider",
        ):
            batch.drop_column(column)
    op.drop_index("ix_datasets_asset_capture", table_name="datasets")
    for column in (
        "quality_status",
        "processing_level",
        "provider_code",
        "dataset_type",
        "mission_id",
        "asset_id",
        "workspace_id",
    ):
        op.drop_index(f"ix_datasets_{column}", table_name="datasets")
    with op.batch_alter_table("datasets") as batch:
        batch.alter_column(
            "status",
            existing_type=sa.String(length=20),
            existing_nullable=False,
            server_default=sa.text("'pending'"),
        )
        batch.drop_constraint("ck_dataset_version", type_="check")
        batch.drop_constraint("ck_dataset_total_size", type_="check")
        batch.drop_constraint("ck_dataset_file_count", type_="check")
        batch.drop_constraint("ck_dataset_resolution", type_="check")
        batch.drop_constraint("fk_datasets_created_by_user_id", type_="foreignkey")
        batch.drop_constraint("fk_datasets_mission_id", type_="foreignkey")
        batch.drop_constraint("fk_datasets_asset_id", type_="foreignkey")
        batch.drop_constraint("fk_datasets_workspace_id", type_="foreignkey")
        for column in (
            "lifecycle_version",
            "created_by_user_id",
            "archived_at",
            "provenance_json",
            "quality_status",
            "processing_level",
            "resolution_unit",
            "resolution",
            "crs",
            "object_prefix",
            "storage_provider",
            "source_reference",
            "provider_code",
            "dataset_type",
            "mission_id",
            "asset_id",
            "workspace_id",
        ):
            batch.drop_column(column)
