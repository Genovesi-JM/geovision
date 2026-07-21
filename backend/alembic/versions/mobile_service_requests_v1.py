"""Add persistent service requests for the mobile customer app.

Revision ID: mobile_service_requests_v1
Revises: merge_schema_heads_v1
"""

from alembic import op
import sqlalchemy as sa

revision = "mobile_service_requests_v1"
down_revision = "merge_schema_heads_v1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mobile_service_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("site_id", sa.String(36), nullable=True),
        sa.Column("site_name", sa.String(200), nullable=False),
        sa.Column("request_type", sa.String(50), nullable=False),
        sa.Column("urgency", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="submitted"),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attachments_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("assigned_team", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_mobile_service_requests_user_id", "mobile_service_requests", ["user_id"])
    op.create_index("ix_mobile_service_requests_site_id", "mobile_service_requests", ["site_id"])


def downgrade():
    op.drop_index("ix_mobile_service_requests_site_id", table_name="mobile_service_requests")
    op.drop_index("ix_mobile_service_requests_user_id", table_name="mobile_service_requests")
    op.drop_table("mobile_service_requests")
