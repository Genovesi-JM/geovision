"""company prepaid entitlements

Revision ID: company_entitlements_v1
Revises: construction_inspections_v1
"""

from alembic import op
import sqlalchemy as sa

revision = "company_entitlements_v1"
down_revision = "construction_inspections_v1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "company_entitlements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tier", sa.String(40), nullable=False, server_default="starter"),
        sa.Column("kit", sa.String(120)),
        sa.Column("sensor_allowance", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("valid_until", sa.DateTime()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_company_entitlements_company_id", "company_entitlements", ["company_id"], unique=True)


def downgrade():
    op.drop_index("ix_company_entitlements_company_id", table_name="company_entitlements")
    op.drop_table("company_entitlements")
