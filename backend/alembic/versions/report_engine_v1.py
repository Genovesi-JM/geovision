"""Add the canonical report generation, review, and publication contract.

Revision ID: report_engine_v1
Revises: kpi_observation_action_v1
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "report_engine_v1"
down_revision = "kpi_observation_action_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=True),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column("acquisition_id", sa.String(36), nullable=True),
        sa.Column("report_type", sa.String(80), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("template_version", sa.String(40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(30), nullable=False, server_default="GENERATING"),
        sa.Column("qa_level", sa.String(30), nullable=False, server_default="HUMAN_REVIEW"),
        sa.Column("context_schema_version", sa.String(40), nullable=False),
        sa.Column("context_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("context_sha256", sa.String(64), nullable=False),
        sa.Column("narrative_provider", sa.String(80), nullable=False),
        sa.Column("narrative_model", sa.String(120), nullable=True),
        sa.Column("narrative_schema_version", sa.String(40), nullable=False),
        sa.Column("narrative_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("qa_result_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("output_dataset_id", sa.String(36), nullable=True),
        sa.Column("output_file_id", sa.String(36), nullable=True),
        sa.Column("supersedes_report_id", sa.String(36), nullable=True),
        sa.Column("generation_key", sa.String(200), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by_user_id", sa.String(36), nullable=True),
        sa.Column("published_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("lifecycle_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "status IN ('GENERATING', 'DRAFT', 'REVIEW_REQUIRED', 'APPROVED', "
            "'PUBLISHED', 'SUPERSEDED')",
            name="ck_report_status",
        ),
        sa.CheckConstraint(
            "qa_level IN ('AUTO_APPROVED', 'HUMAN_REVIEW', 'SPECIALIST_REVIEW')",
            name="ck_report_qa_level",
        ),
        sa.CheckConstraint("revision > 0", name="ck_report_revision"),
        sa.CheckConstraint(
            "lifecycle_version > 0", name="ck_report_lifecycle_version"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["companies.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["accounts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["acquisition_id"], ["acquisitions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["output_dataset_id"], ["datasets.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["output_file_id"], ["dataset_files.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_report_id"], ["reports.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["published_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("generation_key"),
        sa.UniqueConstraint(
            "asset_id", "report_type", "revision", name="uq_report_asset_type_revision"
        ),
    )
    for column in (
        "organization_id",
        "workspace_id",
        "asset_id",
        "acquisition_id",
        "report_type",
        "status",
        "qa_level",
        "context_sha256",
        "output_dataset_id",
        "output_file_id",
        "supersedes_report_id",
        "published_at",
    ):
        op.create_index(f"ix_reports_{column}", "reports", [column])
    op.create_index(
        "ix_reports_scope_status",
        "reports",
        ["organization_id", "workspace_id", "status"],
    )
    op.create_index(
        "ix_reports_asset_type_status",
        "reports",
        ["asset_id", "report_type", "status"],
    )


def downgrade() -> None:
    op.drop_table("reports")
