"""Add canonical service-request journey links and idempotency.

Revision ID: service_request_journey_v1
Revises: integration_registry_v1
"""

from alembic import op
import sqlalchemy as sa


revision = "service_request_journey_v1"
down_revision = "integration_registry_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Historical mobile clients used free text. Normalize known values and
    # safely retain unknown legacy rows at the initial lifecycle state before
    # installing the database invariant.
    op.execute(
        """
        UPDATE mobile_service_requests
        SET status = lower(trim(status))
        WHERE lower(trim(status)) IN (
            'submitted', 'scheduled', 'in_field', 'processing',
            'results_ready', 'delivered', 'completed', 'cancelled', 'rejected'
        )
        """
    )
    op.execute(
        """
        UPDATE mobile_service_requests
        SET status = 'submitted'
        WHERE lower(trim(status)) NOT IN (
            'submitted', 'scheduled', 'in_field', 'processing',
            'results_ready', 'delivered', 'completed', 'cancelled', 'rejected'
        )
        """
    )
    op.execute(
        """
        UPDATE mobile_service_requests
        SET progress_percent = CASE
            WHEN progress_percent < 0 THEN 0
            WHEN progress_percent > 100 THEN 100
            ELSE progress_percent
        END
        """
    )
    with op.batch_alter_table("mobile_service_requests") as batch:
        batch.add_column(sa.Column("organization_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("workspace_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("asset_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("order_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("report_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("idempotency_key", sa.String(160), nullable=True))
        batch.add_column(sa.Column("request_sha256", sa.String(64), nullable=True))
        batch.add_column(
            sa.Column(
                "lifecycle_version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch.create_foreign_key(
            "fk_mobile_service_request_organization",
            "companies",
            ["organization_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_mobile_service_request_workspace",
            "accounts",
            ["workspace_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_mobile_service_request_asset",
            "assets",
            ["asset_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_mobile_service_request_order",
            "orders",
            ["order_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_mobile_service_request_report",
            "reports",
            ["report_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_check_constraint(
            "ck_mobile_service_request_version",
            "lifecycle_version > 0",
        )
        batch.create_check_constraint(
            "ck_mobile_service_request_progress",
            "progress_percent >= 0 AND progress_percent <= 100",
        )
        batch.create_check_constraint(
            "ck_mobile_service_request_status",
            "status IN ('submitted', 'scheduled', 'in_field', 'processing', "
            "'results_ready', 'delivered', 'completed', 'cancelled', 'rejected')",
        )
        batch.create_check_constraint(
            "ck_mobile_service_request_idempotency_digest",
            "(idempotency_key IS NULL AND request_sha256 IS NULL) "
            "OR (idempotency_key IS NOT NULL AND organization_id IS NOT NULL "
            "AND length(request_sha256) = 64)",
        )

    # Adopt every unambiguous legacy site link. The canonical asset mapper
    # guarantees one site asset per legacy identifier. Requests whose old site
    # was already deleted (or whose canonical asset cannot be resolved) remain
    # deliberately quarantined with NULL scope: customer and Operations APIs
    # must not guess a tenant for them. Recovery requires an audited data repair.
    op.execute(
        """
        UPDATE mobile_service_requests
        SET organization_id = (
            SELECT sites.company_id
            FROM sites
            WHERE sites.id = mobile_service_requests.site_id
        )
        WHERE organization_id IS NULL AND site_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE mobile_service_requests
        SET asset_id = (
            SELECT assets.id
            FROM assets
            WHERE assets.legacy_source = 'site'
              AND assets.legacy_source_id = mobile_service_requests.site_id
              AND assets.organization_id = mobile_service_requests.organization_id
              AND assets.status <> 'archived'
            ORDER BY assets.created_at, assets.id
            LIMIT 1
        )
        WHERE asset_id IS NULL
          AND organization_id IS NOT NULL
          AND site_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE mobile_service_requests
        SET workspace_id = (
            SELECT assets.workspace_id
            FROM assets
            WHERE assets.id = mobile_service_requests.asset_id
              AND assets.organization_id = mobile_service_requests.organization_id
        )
        WHERE workspace_id IS NULL AND asset_id IS NOT NULL
        """
    )

    op.create_index(
        "ix_mobile_service_requests_organization_id",
        "mobile_service_requests",
        ["organization_id"],
    )
    op.create_index(
        "ix_mobile_service_requests_workspace_id",
        "mobile_service_requests",
        ["workspace_id"],
    )
    op.create_index(
        "ix_mobile_service_requests_asset_id",
        "mobile_service_requests",
        ["asset_id"],
    )
    op.create_index(
        "ix_mobile_service_requests_order_id",
        "mobile_service_requests",
        ["order_id"],
    )
    op.create_index(
        "ix_mobile_service_requests_report_id",
        "mobile_service_requests",
        ["report_id"],
    )
    op.create_index(
        "uq_mobile_service_request_idempotency",
        "mobile_service_requests",
        ["organization_id", "workspace_id", "user_id", "idempotency_key"],
        unique=True,
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # Account events created after this revision carry an explicit workspace.
    # Adopt historical rows only when the organization has one unambiguous
    # active workspace. Ambiguous rows remain NULL and therefore quarantined
    # from the exact-workspace customer projection.
    with op.batch_alter_table("account_events") as batch:
        batch.add_column(sa.Column("workspace_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_account_event_workspace",
            "accounts",
            ["workspace_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.execute(
        """
        UPDATE account_events
        SET workspace_id = (
            SELECT MIN(accounts.id)
            FROM accounts
            WHERE accounts.organization_id = account_events.company_id
              AND accounts.status = 'active'
        )
        WHERE workspace_id IS NULL
          AND (
              SELECT COUNT(*)
              FROM accounts
              WHERE accounts.organization_id = account_events.company_id
                AND accounts.status = 'active'
          ) = 1
        """
    )
    op.create_index(
        "ix_account_events_workspace_id",
        "account_events",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_account_events_workspace_id",
        table_name="account_events",
    )
    with op.batch_alter_table("account_events") as batch:
        batch.drop_constraint("fk_account_event_workspace", type_="foreignkey")
        batch.drop_column("workspace_id")

    op.drop_index(
        "uq_mobile_service_request_idempotency",
        table_name="mobile_service_requests",
    )
    op.drop_index(
        "ix_mobile_service_requests_report_id",
        table_name="mobile_service_requests",
    )
    op.drop_index(
        "ix_mobile_service_requests_order_id",
        table_name="mobile_service_requests",
    )
    op.drop_index(
        "ix_mobile_service_requests_asset_id",
        table_name="mobile_service_requests",
    )
    op.drop_index(
        "ix_mobile_service_requests_workspace_id",
        table_name="mobile_service_requests",
    )
    op.drop_index(
        "ix_mobile_service_requests_organization_id",
        table_name="mobile_service_requests",
    )
    with op.batch_alter_table("mobile_service_requests") as batch:
        batch.drop_constraint(
            "ck_mobile_service_request_idempotency_digest",
            type_="check",
        )
        batch.drop_constraint("ck_mobile_service_request_progress", type_="check")
        batch.drop_constraint("ck_mobile_service_request_version", type_="check")
        batch.drop_constraint("ck_mobile_service_request_status", type_="check")
        batch.drop_constraint("fk_mobile_service_request_report", type_="foreignkey")
        batch.drop_constraint("fk_mobile_service_request_order", type_="foreignkey")
        batch.drop_constraint("fk_mobile_service_request_asset", type_="foreignkey")
        batch.drop_constraint("fk_mobile_service_request_workspace", type_="foreignkey")
        batch.drop_constraint(
            "fk_mobile_service_request_organization",
            type_="foreignkey",
        )
        batch.drop_column("lifecycle_version")
        batch.drop_column("request_sha256")
        batch.drop_column("idempotency_key")
        batch.drop_column("report_id")
        batch.drop_column("order_id")
        batch.drop_column("asset_id")
        batch.drop_column("workspace_id")
        batch.drop_column("organization_id")
