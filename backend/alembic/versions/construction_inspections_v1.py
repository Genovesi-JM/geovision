"""construction / QR asset inspections

Revision ID: construction_inspections_v1
Revises: iot_hardware_platform_v1
"""

from alembic import op
import sqlalchemy as sa

revision = "construction_inspections_v1"
down_revision = "iot_hardware_platform_v1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "asset_inspections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("iot_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", sa.String(36), nullable=False),
        sa.Column("inspected_by", sa.String(36)),
        sa.Column("inspector_name", sa.String(160)),
        sa.Column("category", sa.String(80), nullable=False, server_default="general"),
        sa.Column("result", sa.String(20), nullable=False, server_default="pass"),
        sa.Column("notes", sa.Text()),
        sa.Column("checklist_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("photos_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    for name, cols in (
        ("ix_asset_inspections_company_id", ["company_id"]),
        ("ix_asset_inspections_asset_id", ["asset_id"]),
        ("ix_asset_inspections_site_id", ["site_id"]),
        ("ix_asset_inspections_created_at", ["created_at"]),
    ):
        op.create_index(name, "asset_inspections", cols)


def downgrade():
    op.drop_table("asset_inspections")
