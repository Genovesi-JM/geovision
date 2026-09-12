"""Version the isolated legacy customer/employee directory database.

This is not the primary authentication/user database. Existing records require
an explicit backup/import rehearsal; never use this revision to infer tenants.
"""

from alembic import op
import sqlalchemy as sa

revision = "accounts_v1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customer_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(256), nullable=False),
        sa.Column("company", sa.String(200)),
        sa.Column("country", sa.String(100)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_customer_accounts_id", "customer_accounts", ["id"])
    op.create_index("ix_customer_accounts_email", "customer_accounts", ["email"], unique=True)
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(256), nullable=False),
        sa.Column("role", sa.String(120), nullable=False),
        sa.Column("department", sa.String(120)),
        sa.Column("phone", sa.String(60)),
        sa.Column("is_active", sa.Boolean()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_employees_id", "employees", ["id"])
    op.create_index("ix_employees_email", "employees", ["email"], unique=True)


def downgrade():
    # Deployment never invokes downgrade; this is only for disposable rehearsal.
    op.drop_table("employees")
    op.drop_table("customer_accounts")
