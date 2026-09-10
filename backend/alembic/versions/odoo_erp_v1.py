"""Durable provider-pinned Odoo ERP synchronization.

Revision ID: odoo_erp_v1
Revises: notification_delivery_v1
"""

from alembic import op
import sqlalchemy as sa


revision = "odoo_erp_v1"
down_revision = "notification_delivery_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("integration_outbox") as batch:
        batch.add_column(
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3")
        )
        batch.add_column(sa.Column("external_model", sa.String(120), nullable=True))
        batch.add_column(sa.Column("last_error_code", sa.String(100), nullable=True))
        batch.add_column(sa.Column("claimed_by", sa.String(100), nullable=True))
        batch.add_column(sa.Column("claimed_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("lease_expires_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("dead_lettered_at", sa.DateTime(), nullable=True))
        batch.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            )
        )
        batch.create_index("ix_integration_outbox_claimed_by", ["claimed_by"])
        batch.create_index(
            "ix_integration_outbox_lease_expires_at", ["lease_expires_at"]
        )

    op.create_table(
        "erp_external_references",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "company_id",
            sa.String(36),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("internal_id", sa.String(100), nullable=False),
        sa.Column("external_model", sa.String(120), nullable=True),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("invoice_status", sa.String(100), nullable=True),
        sa.Column("stock_status", sa.String(100), nullable=True),
        sa.Column("purchase_status", sa.String(100), nullable=True),
        sa.Column("provider_updated_at", sa.DateTime(), nullable=True),
        sa.Column("last_callback_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "provider",
            "resource_type",
            "internal_id",
            name="uq_erp_reference_internal",
        ),
        sa.UniqueConstraint(
            "provider",
            "external_model",
            "external_id",
            name="uq_erp_reference_external",
        ),
    )
    op.create_index(
        "ix_erp_external_references_company_id",
        "erp_external_references",
        ["company_id"],
    )
    op.create_index(
        "ix_erp_external_references_provider",
        "erp_external_references",
        ["provider"],
    )
    op.create_index(
        "ix_erp_external_references_internal_id",
        "erp_external_references",
        ["internal_id"],
    )
    op.create_index(
        "ix_erp_external_references_external_id",
        "erp_external_references",
        ["external_id"],
    )
    op.create_index(
        "ix_erp_reference_company_resource",
        "erp_external_references",
        ["company_id", "resource_type"],
    )

    op.create_table(
        "erp_callback_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("event_id", sa.String(160), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("signature_verified", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("internal_id", sa.String(100), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("outcome", sa.String(30), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "outcome IN ('PROCESSED', 'DUPLICATE', 'IGNORED')",
            name="ck_erp_callback_outcome",
        ),
        sa.UniqueConstraint(
            "provider", "event_id", name="uq_erp_callback_provider_event"
        ),
    )
    op.create_index(
        "ix_erp_callback_receipts_internal_id",
        "erp_callback_receipts",
        ["internal_id"],
    )


def downgrade() -> None:
    op.drop_table("erp_callback_receipts")
    op.drop_table("erp_external_references")
    with op.batch_alter_table("integration_outbox") as batch:
        batch.drop_index("ix_integration_outbox_lease_expires_at")
        batch.drop_index("ix_integration_outbox_claimed_by")
        batch.drop_column("updated_at")
        batch.drop_column("dead_lettered_at")
        batch.drop_column("lease_expires_at")
        batch.drop_column("claimed_at")
        batch.drop_column("claimed_by")
        batch.drop_column("last_error_code")
        batch.drop_column("external_model")
        batch.drop_column("max_attempts")
