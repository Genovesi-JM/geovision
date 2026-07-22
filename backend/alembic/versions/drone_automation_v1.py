"""Add tenant-isolated aircraft registry and guarded mission plans."""

from alembic import op
import sqlalchemy as sa

revision = "drone_automation_v1"
down_revision = "erp_realtime_account_v1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "drone_aircraft",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("site_id", sa.String(36), sa.ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("manufacturer", sa.String(50), nullable=False, server_default="DJI"),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("serial_number", sa.String(150)),
        sa.Column("provider", sa.String(50), nullable=False, server_default="manual_import"),
        sa.Column("connection_mode", sa.String(40), nullable=False, server_default="media_import"),
        sa.Column("sdk_supported", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(30), nullable=False, server_default="registered"),
        sa.Column("capabilities_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "drone_missions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("site_id", sa.String(36), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("aircraft_id", sa.String(36), sa.ForeignKey("drone_aircraft.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("mission_type", sa.String(40), nullable=False, server_default="mapping_grid"),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("altitude_m", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("speed_mps", sa.Numeric(6, 2), nullable=False, server_default="5"),
        sa.Column("front_overlap_percent", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("side_overlap_percent", sa.Integer(), nullable=False, server_default="70"),
        sa.Column("boundary_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("route_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("checklist_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("provider_reference", sa.String(200)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("drone_missions")
    op.drop_table("drone_aircraft")
