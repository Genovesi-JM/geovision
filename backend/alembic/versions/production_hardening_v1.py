"""production hardening v1 — auth identities, refresh tokens, contacts, KPIs, audit

Revision ID: prod_hardening_v1
Revises: enterprise_complete_v1
Create Date: 2026-02-13
"""

from alembic import op
import sqlalchemy as sa

revision = "prod_hardening_v1"
down_revision = "enterprise_complete_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Auth Identity Linking ──
    op.create_table(
        "auth_identities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_user_id", sa.String(255), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("raw_data", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_auth_identities_provider_sub", "auth_identities", ["provider", "provider_user_id"], unique=True)

    # ── Refresh Tokens ──
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(), unique=True, index=True, nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("family_id", sa.String(36), nullable=False, index=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked", sa.Boolean(), default=False, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # ── Contact Methods ──
    op.create_table(
        "contact_methods",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("value", sa.String(500), nullable=False),
        sa.Column("environment", sa.String(20), nullable=False, server_default="prod"),
        sa.Column("is_public", sa.Boolean(), default=True, nullable=False),
        sa.Column("sort_order", sa.Integer(), default=0, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # ── KPI Definitions ──
    op.create_table(
        "kpi_definitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("sector", sa.String(50), nullable=False, index=True),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(100), nullable=True),
        sa.Column("sort_order", sa.Integer(), default=0, nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # ── KPI Values ──
    op.create_table(
        "kpi_values",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kpi_definition_id", sa.String(36), sa.ForeignKey("kpi_definitions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("site_id", sa.String(36), nullable=True, index=True),
        sa.Column("dataset_id", sa.String(36), nullable=True),
        sa.Column("value", sa.String(500), nullable=False),
        sa.Column("numeric_value", sa.Numeric(14, 4), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # ── Audit Log ──
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=True, index=True),
        sa.Column("user_email", sa.String(), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("resource_id", sa.String(36), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("kpi_values")
    op.drop_table("kpi_definitions")
    op.drop_table("contact_methods")
    op.drop_table("refresh_tokens")
    op.drop_table("auth_identities")
