"""Generalize the operational ledger into a durable transactional outbox.

Revision ID: durable_events_v1
Revises: datasets_storage_v2
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "durable_events_v1"
down_revision = "datasets_storage_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("operational_domain_events") as batch:
        batch.alter_column(
            "aggregate_id",
            existing_type=sa.String(length=36),
            type_=sa.String(length=100),
            existing_nullable=False,
        )
        batch.add_column(
            sa.Column(
                "topic",
                sa.String(length=120),
                nullable=False,
                server_default="geovision.domain.v1",
            )
        )
        batch.add_column(
            sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(sa.Column("correlation_id", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("causation_id", sa.String(length=100), nullable=True))
        batch.add_column(
            sa.Column(
                "status", sa.String(length=20), nullable=False, server_default="pending"
            )
        )
        batch.add_column(sa.Column("next_attempt_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("last_error", sa.Text(), nullable=True))
        batch.add_column(sa.Column("claimed_by", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("claimed_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("dead_lettered_at", sa.DateTime(), nullable=True))
        batch.create_check_constraint(
            "ck_operational_domain_event_schema_version", "schema_version > 0"
        )
        batch.create_check_constraint(
            "ck_operational_domain_event_status",
            "status IN ('pending', 'processing', 'retry', 'published', 'dead_letter')",
        )

    op.execute(
        sa.text(
            """
            UPDATE operational_domain_events
            SET status = CASE
                    WHEN published_at IS NOT NULL THEN 'published'
                    ELSE 'pending'
                END,
                correlation_id = COALESCE(correlation_id, id)
            """
        )
    )
    op.create_index(
        "ix_operational_domain_events_status",
        "operational_domain_events",
        ["status"],
    )
    op.create_index(
        "ix_operational_domain_events_next_attempt_at",
        "operational_domain_events",
        ["next_attempt_at"],
    )
    op.create_index(
        "ix_operational_domain_events_correlation_id",
        "operational_domain_events",
        ["correlation_id"],
    )
    op.create_index(
        "ix_operational_domain_events_due",
        "operational_domain_events",
        ["status", "next_attempt_at", "occurred_at"],
    )

    op.create_table(
        "event_consumer_receipts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("consumer_name", sa.String(length=100), nullable=False),
        sa.Column("event_id", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "consumer_name", "event_id", name="uq_event_consumer_receipt"
        ),
    )
    op.create_index(
        "ix_event_consumer_receipts_event_type",
        "event_consumer_receipts",
        ["event_type"],
    )
    op.create_index(
        "ix_event_consumer_receipts_consumer",
        "event_consumer_receipts",
        ["consumer_name", "processed_at"],
    )

    op.create_table(
        "event_delivery_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("worker_id", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "attempt_number > 0", name="ck_event_delivery_attempt_number"
        ),
        sa.CheckConstraint(
            "outcome IN ('published', 'retry', 'dead_letter')",
            name="ck_event_delivery_attempt_outcome",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_event_delivery_attempts_event_id",
        "event_delivery_attempts",
        ["event_id"],
    )
    op.create_index(
        "ix_event_delivery_attempts_event_attempt",
        "event_delivery_attempts",
        ["event_id", "attempt_number"],
    )
    op.create_index(
        "ix_dataset_files_storage_object",
        "dataset_files",
        ["storage_provider", "storage_key", "deleted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_dataset_files_storage_object", table_name="dataset_files")
    op.drop_index(
        "ix_event_delivery_attempts_event_attempt",
        table_name="event_delivery_attempts",
    )
    op.drop_index(
        "ix_event_delivery_attempts_event_id", table_name="event_delivery_attempts"
    )
    op.drop_table("event_delivery_attempts")
    op.drop_index(
        "ix_event_consumer_receipts_consumer", table_name="event_consumer_receipts"
    )
    op.drop_index(
        "ix_event_consumer_receipts_event_type", table_name="event_consumer_receipts"
    )
    op.drop_table("event_consumer_receipts")
    for index_name in (
        "ix_operational_domain_events_due",
        "ix_operational_domain_events_correlation_id",
        "ix_operational_domain_events_next_attempt_at",
        "ix_operational_domain_events_status",
    ):
        op.drop_index(index_name, table_name="operational_domain_events")
    with op.batch_alter_table("operational_domain_events") as batch:
        batch.drop_constraint("ck_operational_domain_event_status", type_="check")
        batch.drop_constraint(
            "ck_operational_domain_event_schema_version", type_="check"
        )
        for column in (
            "dead_lettered_at",
            "claimed_at",
            "claimed_by",
            "last_error",
            "next_attempt_at",
            "status",
            "causation_id",
            "correlation_id",
            "schema_version",
            "topic",
        ):
            batch.drop_column(column)
        batch.alter_column(
            "aggregate_id",
            existing_type=sa.String(length=100),
            type_=sa.String(length=36),
            existing_nullable=False,
        )
