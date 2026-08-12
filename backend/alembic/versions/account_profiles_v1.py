"""Persist customer type, use cases, and dashboard profile on accounts.

Revision ID: account_profiles_v1
Revises: company_entitlements_v1
"""

from alembic import op
import sqlalchemy as sa


revision = "account_profiles_v1"
down_revision = "company_entitlements_v1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("accounts") as batch:
        batch.add_column(sa.Column("customer_type", sa.String(), nullable=False, server_default="farm"))
        batch.add_column(sa.Column("dashboard_profile", sa.String(), nullable=False, server_default="farm"))
        batch.add_column(sa.Column("use_cases", sa.Text(), nullable=False, server_default="[]"))


def downgrade():
    with op.batch_alter_table("accounts") as batch:
        batch.drop_column("use_cases")
        batch.drop_column("dashboard_profile")
        batch.drop_column("customer_type")
