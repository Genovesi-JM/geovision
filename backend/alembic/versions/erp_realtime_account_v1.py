"""ERP outbox and customer account event stream.

Revision ID: erp_realtime_account_v1
Revises: mobile_service_requests_v1
"""

from alembic import op
import sqlalchemy as sa

revision = "erp_realtime_account_v1"
down_revision = "mobile_service_requests_v1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "integration_outbox",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=True),
        sa.Column("provider", sa.String(30), nullable=False, server_default="erpnext"),
        sa.Column("aggregate_type", sa.String(50), nullable=False),
        sa.Column("aggregate_id", sa.String(100), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("external_id", sa.String(200), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_integration_outbox_company_id", "integration_outbox", ["company_id"])
    op.create_index("ix_integration_outbox_status", "integration_outbox", ["status"])
    op.create_index("ix_integration_outbox_idempotency_key", "integration_outbox", ["idempotency_key"], unique=True)
    op.create_table(
        "account_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_account_events_company_id", "account_events", ["company_id"])
    op.create_index("ix_account_events_event_type", "account_events", ["event_type"])
    op.create_index("ix_account_events_created_at", "account_events", ["created_at"])


def downgrade():
    op.drop_table("account_events")
    op.drop_table("integration_outbox")
