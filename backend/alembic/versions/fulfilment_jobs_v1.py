"""Separate commercial orders from executable fulfilment jobs.

Revision ID: fulfilment_jobs_v1
Revises: operations_resources_v1
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "fulfilment_jobs_v1"
down_revision = "operations_resources_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fulfilment_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_number", sa.String(length=40), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("order_item_id", sa.String(length=36), nullable=True),
        sa.Column("asset_id", sa.String(length=36), nullable=True),
        sa.Column("job_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="NORMAL"),
        sa.Column("state", sa.String(length=30), nullable=False, server_default="PLANNED"),
        sa.Column("resume_state", sa.String(length=30), nullable=True),
        sa.Column("assigned_contractor_id", sa.String(length=36), nullable=True),
        sa.Column("assigned_user_id", sa.String(length=36), nullable=True),
        sa.Column("scheduled_start", sa.DateTime(), nullable=True),
        sa.Column("scheduled_end", sa.DateTime(), nullable=True),
        sa.Column("actual_start", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("requirements_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("direct_cost_amount", sa.Integer(), nullable=True),
        sa.Column("cost_currency", sa.String(length=5), nullable=True),
        sa.Column("cost_reference", sa.String(length=160), nullable=True),
        sa.Column("plan_key", sa.String(length=180), nullable=True),
        sa.Column("lifecycle_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "priority IN ('LOW', 'NORMAL', 'HIGH', 'URGENT')",
            name="ck_fulfilment_job_priority",
        ),
        sa.CheckConstraint(
            "state IN ('PLANNED', 'READY', 'BLOCKED', 'ASSIGNED', 'SCHEDULED', "
            "'IN_PROGRESS', 'WAITING_INPUT', 'QA_REVIEW', 'COMPLETED', "
            "'CANCELLED', 'FAILED')",
            name="ck_fulfilment_job_state",
        ),
        sa.CheckConstraint(
            "NOT (assigned_contractor_id IS NOT NULL AND assigned_user_id IS NOT NULL)",
            name="ck_fulfilment_job_single_assignee",
        ),
        sa.CheckConstraint(
            "scheduled_end IS NULL OR scheduled_start IS NULL OR scheduled_end > scheduled_start",
            name="ck_fulfilment_job_schedule_window",
        ),
        sa.CheckConstraint(
            "direct_cost_amount IS NULL OR direct_cost_amount >= 0",
            name="ck_fulfilment_job_cost_nonnegative",
        ),
        sa.CheckConstraint("lifecycle_version > 0", name="ck_fulfilment_job_version"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["assigned_contractor_id"], ["operations_contractors.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_item_id"], ["order_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_number", name="uq_fulfilment_job_number"),
        sa.UniqueConstraint("plan_key", name="uq_fulfilment_job_plan_key"),
    )
    for column in (
        "job_number",
        "order_id",
        "order_item_id",
        "asset_id",
        "job_type",
        "priority",
        "state",
        "assigned_contractor_id",
        "assigned_user_id",
        "plan_key",
    ):
        op.create_index(
            f"ix_fulfilment_jobs_{column}",
            "fulfilment_jobs",
            [column],
            unique=column in {"job_number", "plan_key"},
        )

    op.create_table(
        "fulfilment_job_dependencies",
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("depends_on_job_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "job_id <> depends_on_job_id", name="ck_fulfilment_job_no_self_dependency"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["job_id"], ["fulfilment_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["depends_on_job_id"], ["fulfilment_jobs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("job_id", "depends_on_job_id"),
    )
    op.create_index(
        "ix_fulfilment_job_dependencies_upstream",
        "fulfilment_job_dependencies",
        ["depends_on_job_id"],
        unique=False,
    )

    op.create_table(
        "operational_domain_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("aggregate_type", sa.String(length=50), nullable=False),
        sa.Column("aggregate_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("publish_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "publish_attempts >= 0", name="ck_operational_domain_event_attempts"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_operational_domain_event_idempotency_key"
        ),
    )
    for column in ("aggregate_type", "aggregate_id", "event_type", "idempotency_key"):
        op.create_index(
            f"ix_operational_domain_events_{column}",
            "operational_domain_events",
            [column],
            unique=column == "idempotency_key",
        )

    with op.batch_alter_table("contractor_assignments") as batch:
        batch.create_foreign_key(
            "fk_contractor_assignments_fulfilment_job_id",
            "fulfilment_jobs",
            ["fulfilment_job_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("contractor_assignments") as batch:
        batch.drop_constraint(
            "fk_contractor_assignments_fulfilment_job_id", type_="foreignkey"
        )
    # Phase 9 keeps this nullable compatibility column. Clear references before
    # removing their Phase 10 target so a later re-upgrade can recreate the FK.
    op.execute(sa.text("UPDATE contractor_assignments SET fulfilment_job_id = NULL"))

    for column in ("idempotency_key", "event_type", "aggregate_id", "aggregate_type"):
        op.drop_index(
            f"ix_operational_domain_events_{column}",
            table_name="operational_domain_events",
        )
    op.drop_table("operational_domain_events")

    op.drop_index(
        "ix_fulfilment_job_dependencies_upstream",
        table_name="fulfilment_job_dependencies",
    )
    op.drop_table("fulfilment_job_dependencies")

    for column in (
        "plan_key",
        "assigned_user_id",
        "assigned_contractor_id",
        "state",
        "priority",
        "job_type",
        "asset_id",
        "order_item_id",
        "order_id",
        "job_number",
    ):
        op.drop_index(f"ix_fulfilment_jobs_{column}", table_name="fulfilment_jobs")
    op.drop_table("fulfilment_jobs")
