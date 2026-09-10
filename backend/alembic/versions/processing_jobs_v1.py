"""Add provider-neutral photogrammetry processing jobs.

Revision ID: processing_jobs_v1
Revises: durable_events_v1
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "processing_jobs_v1"
down_revision = "durable_events_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("asset_id", sa.String(length=36), nullable=True),
        sa.Column("acquisition_id", sa.String(length=36), nullable=True),
        sa.Column("fulfilment_job_id", sa.String(length=36), nullable=True),
        sa.Column("provider_code", sa.String(length=80), nullable=False),
        sa.Column("provider_job_reference", sa.String(length=240), nullable=True),
        sa.Column(
            "requested_outputs_json", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column("options_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="REQUESTED"
        ),
        sa.Column(
            "progress_percent", sa.Float(), nullable=False, server_default="0"
        ),
        sa.Column("stage", sa.String(length=120), nullable=True),
        sa.Column("processor_name", sa.String(length=120), nullable=True),
        sa.Column("processor_version", sa.String(length=120), nullable=True),
        sa.Column("estimated_cost_amount", sa.Integer(), nullable=True),
        sa.Column("actual_cost_amount", sa.Integer(), nullable=True),
        sa.Column(
            "cost_currency", sa.String(length=5), nullable=False, server_default="USD"
        ),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("quality_report_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("poll_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "submission_generation", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("next_poll_at", sa.DateTime(), nullable=True),
        sa.Column("claimed_by", sa.String(length=100), nullable=True),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("lifecycle_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('REQUESTED', 'VALIDATING', 'SUBMITTED', 'RUNNING', "
            "'RETRY_WAIT', 'NEEDS_REVIEW', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_processing_job_status",
        ),
        sa.CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_processing_job_progress",
        ),
        sa.CheckConstraint(
            "estimated_cost_amount IS NULL OR estimated_cost_amount >= 0",
            name="ck_processing_job_estimated_cost",
        ),
        sa.CheckConstraint(
            "actual_cost_amount IS NULL OR actual_cost_amount >= 0",
            name="ck_processing_job_actual_cost",
        ),
        sa.CheckConstraint(
            "retry_count >= 0 AND max_retries >= 0 AND poll_count >= 0 "
            "AND submission_generation >= 0",
            name="ck_processing_job_attempt_counts",
        ),
        sa.CheckConstraint(
            "lifecycle_version > 0", name="ck_processing_job_version"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["companies.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["accounts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["acquisition_id"], ["acquisitions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["fulfilment_job_id"], ["fulfilment_jobs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint(
            "provider_code",
            "provider_job_reference",
            name="uq_processing_job_provider_reference",
        ),
    )
    for column in (
        "organization_id",
        "workspace_id",
        "asset_id",
        "acquisition_id",
        "fulfilment_job_id",
        "provider_code",
        "status",
        "next_poll_at",
        "idempotency_key",
    ):
        op.create_index(f"ix_processing_jobs_{column}", "processing_jobs", [column])
    op.create_index(
        "ix_processing_jobs_due",
        "processing_jobs",
        ["status", "next_poll_at", "created_at"],
    )

    op.create_table(
        "processing_job_sources",
        sa.Column("processing_job_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "sequence >= 0", name="ck_processing_job_source_sequence"
        ),
        sa.ForeignKeyConstraint(
            ["processing_job_id"], ["processing_jobs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("processing_job_id", "dataset_id"),
    )
    op.create_index(
        "ix_processing_job_sources_dataset_id",
        "processing_job_sources",
        ["dataset_id"],
    )

    op.create_table(
        "processing_job_outputs",
        sa.Column("processing_job_id", sa.String(length=36), nullable=False),
        sa.Column("output_type", sa.String(length=80), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column(
            "quality_status",
            sa.String(length=30),
            nullable=False,
            server_default="PASSED",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "quality_status IN ('PASSED', 'WARNING', 'FAILED')",
            name="ck_processing_job_output_quality",
        ),
        sa.ForeignKeyConstraint(
            ["processing_job_id"], ["processing_jobs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("processing_job_id", "output_type"),
        sa.UniqueConstraint("dataset_id"),
    )
    op.create_index(
        "ix_processing_job_outputs_dataset_id",
        "processing_job_outputs",
        ["dataset_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_processing_job_outputs_dataset_id", table_name="processing_job_outputs"
    )
    op.drop_table("processing_job_outputs")
    op.drop_index(
        "ix_processing_job_sources_dataset_id", table_name="processing_job_sources"
    )
    op.drop_table("processing_job_sources")
    op.drop_index("ix_processing_jobs_due", table_name="processing_jobs")
    for column in reversed(
        (
            "organization_id",
            "workspace_id",
            "asset_id",
            "acquisition_id",
            "fulfilment_job_id",
            "provider_code",
            "status",
            "next_poll_at",
            "idempotency_key",
        )
    ):
        op.drop_index(f"ix_processing_jobs_{column}", table_name="processing_jobs")
    op.drop_table("processing_jobs")
