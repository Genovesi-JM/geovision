"""Persist audit context, report provenance, and internal unit economics.

Revision ID: trust_economics_v1
Revises: odoo_erp_v1
"""

from alembic import op
import json
import sqlalchemy as sa


revision = "trust_economics_v1"
down_revision = "odoo_erp_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("audit_log") as batch:
        batch.add_column(
            sa.Column(
                "organization_id",
                sa.String(36),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "workspace_id",
                sa.String(36),
                nullable=True,
            )
        )
        batch.add_column(sa.Column("request_id", sa.String(100), nullable=True))
        batch.add_column(sa.Column("correlation_id", sa.String(100), nullable=True))
        batch.add_column(
            sa.Column(
                "outcome",
                sa.String(20),
                nullable=False,
                server_default="UNKNOWN",
            )
        )
        batch.create_check_constraint(
            "ck_audit_log_outcome",
            "outcome IN ('UNKNOWN', 'SUCCESS', 'FAILURE', 'DENIED')",
        )
        batch.create_foreign_key(
            "fk_audit_log_organization_id_companies",
            "companies",
            ["organization_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_audit_log_workspace_id_accounts",
            "accounts",
            ["workspace_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_audit_log_organization_id", ["organization_id"])
        batch.create_index("ix_audit_log_workspace_id", ["workspace_id"])
        batch.create_index("ix_audit_log_request_id", ["request_id"])
        batch.create_index("ix_audit_log_correlation_id", ["correlation_id"])
        batch.create_index("ix_audit_log_outcome", ["outcome"])

    with op.batch_alter_table("reports") as batch:
        batch.add_column(
            sa.Column(
                "provenance_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )
        batch.add_column(
            sa.Column(
                "narrative_model_version",
                sa.String(120),
                nullable=False,
                server_default="legacy-unversioned",
            )
        )

    # Preserve the original legacy source ledger while attaching the immutable
    # compatibility-adapter version used to materialize each acquisition.
    connection = op.get_bind()
    legacy_versions = {
        "drone_mission": "geovision-legacy-drone-sync-v1.0.0",
        "asset_inspection": "geovision-legacy-inspection-sync-v1.0.0",
    }
    legacy_rows = connection.execute(
        sa.text(
            "SELECT id, legacy_source, provenance_json FROM acquisitions "
            "WHERE legacy_source IN ('drone_mission', 'asset_inspection')"
        )
    ).mappings()
    for row in legacy_rows:
        try:
            provenance = json.loads(row["provenance_json"] or "{}")
        except (TypeError, ValueError):
            provenance = {}
        if not isinstance(provenance, dict):
            provenance = {}
        provenance.setdefault("adapter_version", legacy_versions[row["legacy_source"]])
        connection.execute(
            sa.text(
                "UPDATE acquisitions SET provenance_json = :provenance "
                "WHERE id = :acquisition_id"
            ),
            {
                "provenance": json.dumps(
                    provenance,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                "acquisition_id": row["id"],
            },
        )
    # Historical KPI rows could contain free-form dataset identifiers before
    # this relationship became durable. Preserve the KPI while dropping any
    # unverifiable source link before the foreign key is added.
    op.execute(
        "UPDATE kpi_values SET dataset_id = NULL "
        "WHERE dataset_id IS NOT NULL AND NOT EXISTS "
        "(SELECT 1 FROM datasets WHERE datasets.id = kpi_values.dataset_id)"
    )
    with op.batch_alter_table("kpi_values") as batch:
        batch.create_foreign_key(
            "fk_kpi_values_dataset_id_datasets",
            "datasets",
            ["dataset_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_kpi_values_dataset_id", ["dataset_id"])

    op.create_table(
        "provider_usage",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "order_id",
            sa.String(36),
            sa.ForeignKey("orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "order_item_id",
            sa.String(36),
            sa.ForeignKey("order_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "catalog_item_id",
            sa.String(50),
            sa.ForeignKey("catalog_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "asset_id",
            sa.String(36),
            sa.ForeignKey("assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "acquisition_id",
            sa.String(36),
            sa.ForeignKey("acquisitions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "dataset_id",
            sa.String(36),
            sa.ForeignKey("datasets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "processing_job_id",
            sa.String(36),
            sa.ForeignKey("processing_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "fulfilment_job_id",
            sa.String(36),
            sa.ForeignKey("fulfilment_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "intelligence_acquisition_id",
            sa.String(36),
            sa.ForeignKey("intelligence_acquisitions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "notification_delivery_id",
            sa.String(36),
            sa.ForeignKey("notification_deliveries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "report_id",
            sa.String(36),
            sa.ForeignKey("reports.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("service", sa.String(100), nullable=False),
        sa.Column("usage_type", sa.String(60), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("currency", sa.String(5), nullable=True),
        sa.Column("unit_cost", sa.Numeric(20, 6), nullable=True),
        sa.Column("total_cost", sa.Numeric(20, 4), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("provider_reference", sa.String(200), nullable=True),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("quantity > 0", name="ck_provider_usage_quantity_positive"),
        sa.CheckConstraint(
            "unit_cost IS NULL OR unit_cost >= 0",
            name="ck_provider_usage_unit_cost_nonnegative",
        ),
        sa.CheckConstraint(
            "total_cost IS NULL OR total_cost >= 0",
            name="ck_provider_usage_total_cost_nonnegative",
        ),
        sa.CheckConstraint(
            "(total_cost IS NULL AND currency IS NULL AND unit_cost IS NULL) OR "
            "(total_cost IS NOT NULL AND currency IS NOT NULL)",
            name="ck_provider_usage_cost_currency",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_provider_usage_org_idempotency",
        ),
    )
    op.create_index("ix_provider_usage_organization_id", "provider_usage", ["organization_id"])
    op.create_index("ix_provider_usage_workspace_id", "provider_usage", ["workspace_id"])
    op.create_index("ix_provider_usage_order_id", "provider_usage", ["order_id"])
    op.create_index("ix_provider_usage_order_item_id", "provider_usage", ["order_item_id"])
    op.create_index("ix_provider_usage_catalog_item_id", "provider_usage", ["catalog_item_id"])
    op.create_index("ix_provider_usage_asset_id", "provider_usage", ["asset_id"])
    op.create_index("ix_provider_usage_acquisition_id", "provider_usage", ["acquisition_id"])
    op.create_index("ix_provider_usage_dataset_id", "provider_usage", ["dataset_id"])
    op.create_index("ix_provider_usage_processing_job_id", "provider_usage", ["processing_job_id"])
    op.create_index("ix_provider_usage_fulfilment_job_id", "provider_usage", ["fulfilment_job_id"])
    op.create_index(
        "ix_provider_usage_intelligence_acquisition_id",
        "provider_usage",
        ["intelligence_acquisition_id"],
    )
    op.create_index(
        "ix_provider_usage_notification_delivery_id",
        "provider_usage",
        ["notification_delivery_id"],
    )
    op.create_index("ix_provider_usage_report_id", "provider_usage", ["report_id"])
    op.create_index("ix_provider_usage_provider", "provider_usage", ["provider"])
    op.create_index(
        "ix_provider_usage_provider_reference",
        "provider_usage",
        ["provider", "provider_reference"],
    )
    op.create_index("ix_provider_usage_occurred_at", "provider_usage", ["occurred_at"])
    op.create_index(
        "ix_provider_usage_scope_currency",
        "provider_usage",
        ["organization_id", "order_id", "currency"],
    )

    op.create_table(
        "internal_costs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "order_id",
            sa.String(36),
            sa.ForeignKey("orders.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "order_item_id",
            sa.String(36),
            sa.ForeignKey("order_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "catalog_item_id",
            sa.String(50),
            sa.ForeignKey("catalog_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "asset_id",
            sa.String(36),
            sa.ForeignKey("assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "fulfilment_job_id",
            sa.String(36),
            sa.ForeignKey("fulfilment_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "contractor_assignment_id",
            sa.String(36),
            sa.ForeignKey("contractor_assignments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("cost_type", sa.String(40), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("currency", sa.String(5), nullable=False),
        sa.Column("incurred_at", sa.DateTime(), nullable=False),
        sa.Column("reference", sa.String(200), nullable=True),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount > 0", name="ck_internal_cost_amount_positive"),
        sa.CheckConstraint(
            "cost_type IN ('CONTRACTOR', 'TRAVEL', 'PROCESSING', 'EQUIPMENT', "
            "'SHIPPING', 'SPECIALIST_REVIEW', 'PROVIDER', 'OTHER')",
            name="ck_internal_cost_type",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_internal_cost_org_idempotency",
        ),
    )
    op.create_index("ix_internal_costs_organization_id", "internal_costs", ["organization_id"])
    op.create_index("ix_internal_costs_workspace_id", "internal_costs", ["workspace_id"])
    op.create_index("ix_internal_costs_order_id", "internal_costs", ["order_id"])
    op.create_index("ix_internal_costs_order_item_id", "internal_costs", ["order_item_id"])
    op.create_index("ix_internal_costs_catalog_item_id", "internal_costs", ["catalog_item_id"])
    op.create_index("ix_internal_costs_asset_id", "internal_costs", ["asset_id"])
    op.create_index("ix_internal_costs_fulfilment_job_id", "internal_costs", ["fulfilment_job_id"])
    op.create_index(
        "ix_internal_costs_contractor_assignment_id",
        "internal_costs",
        ["contractor_assignment_id"],
    )
    op.create_index(
        "ix_internal_costs_scope_currency",
        "internal_costs",
        ["organization_id", "order_id", "currency"],
    )


def downgrade() -> None:
    op.drop_table("internal_costs")
    op.drop_table("provider_usage")

    with op.batch_alter_table("kpi_values") as batch:
        batch.drop_index("ix_kpi_values_dataset_id")
        batch.drop_constraint(
            "fk_kpi_values_dataset_id_datasets", type_="foreignkey"
        )

    with op.batch_alter_table("reports") as batch:
        batch.drop_column("narrative_model_version")
        batch.drop_column("provenance_json")

    with op.batch_alter_table("audit_log") as batch:
        batch.drop_index("ix_audit_log_outcome")
        batch.drop_index("ix_audit_log_correlation_id")
        batch.drop_index("ix_audit_log_request_id")
        batch.drop_index("ix_audit_log_workspace_id")
        batch.drop_index("ix_audit_log_organization_id")
        batch.drop_constraint("ck_audit_log_outcome", type_="check")
        batch.drop_constraint(
            "fk_audit_log_workspace_id_accounts", type_="foreignkey"
        )
        batch.drop_constraint(
            "fk_audit_log_organization_id_companies", type_="foreignkey"
        )
        batch.drop_column("outcome")
        batch.drop_column("correlation_id")
        batch.drop_column("request_id")
        batch.drop_column("workspace_id")
        batch.drop_column("organization_id")
