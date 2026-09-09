"""Add secure one-time invitations and deep-link targets.

Revision ID: invitation_onboarding_v1
Revises: generic_assets_postgis_v1
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "invitation_onboarding_v1"
down_revision = "generic_assets_postgis_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invitations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_prefix", sa.String(length=12), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("membership_id", sa.String(length=36), nullable=False),
        sa.Column("target_email", sa.String(), nullable=False),
        sa.Column("pending_email_key", sa.String(), nullable=True),
        sa.Column("identity_hint", sa.String(length=200), nullable=True),
        sa.Column("intended_role", sa.String(length=30), nullable=False),
        sa.Column(
            "target_type",
            sa.String(length=30),
            nullable=False,
            server_default="workspace",
        ),
        sa.Column("target_id", sa.String(length=36), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="pending"
        ),
        sa.Column("invited_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("accepted_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_invitation_status",
        ),
        sa.CheckConstraint(
            "intended_role IN ('admin', 'manager', 'member', 'viewer', 'finance')",
            name="ck_invitation_customer_role",
        ),
        sa.CheckConstraint(
            "target_type IN ('workspace', 'asset', 'report', 'service_result', 'order')",
            name="ck_invitation_target_type",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"], ["company_users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["companies.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["accounts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "pending_email_key",
            name="uq_invitations_pending_org_email",
        ),
    )
    op.create_index(
        "ix_invitations_token_hash",
        "invitations",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_invitations_organization_id",
        "invitations",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_invitations_workspace_id",
        "invitations",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_invitations_membership_id",
        "invitations",
        ["membership_id"],
        unique=False,
    )
    op.create_index(
        "ix_invitations_status_expires",
        "invitations",
        ["status", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_invitations_status_expires", table_name="invitations")
    op.drop_index("ix_invitations_membership_id", table_name="invitations")
    op.drop_index("ix_invitations_workspace_id", table_name="invitations")
    op.drop_index("ix_invitations_organization_id", table_name="invitations")
    op.drop_index("ix_invitations_token_hash", table_name="invitations")
    op.drop_table("invitations")
