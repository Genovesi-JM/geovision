"""Add the versioned KPI, observation, and action intelligence contract.

Revision ID: kpi_observation_action_v1
Revises: iot_edge_contract_v1
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "kpi_observation_action_v1"
down_revision = "iot_edge_contract_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("kpi_definitions") as batch:
        batch.add_column(
            sa.Column("name", sa.String(200), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column("calculator", sa.String(160), nullable=False, server_default="legacy")
        )
        batch.add_column(
            sa.Column(
                "calculator_version",
                sa.String(40),
                nullable=False,
                server_default="legacy-1",
            )
        )
        batch.add_column(
            sa.Column(
                "importance",
                sa.String(20),
                nullable=False,
                server_default="TECHNICAL",
            )
        )
        batch.add_column(
            sa.Column("display_format_json", sa.Text(), nullable=False, server_default="{}")
        )
        batch.add_column(
            sa.Column("status_policy_json", sa.Text(), nullable=False, server_default="{}")
        )
        batch.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
        batch.create_check_constraint(
            "ck_kpi_definition_importance",
            "importance IN ('PRIMARY', 'SECONDARY', 'TECHNICAL')",
        )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE kpi_definitions
               SET name = label,
                   calculator = CASE
                       WHEN calculator = 'legacy' THEN key
                       ELSE calculator
                   END,
                   updated_at = created_at
            """
        )
    )
    op.create_index(
        "ix_kpi_definitions_importance", "kpi_definitions", ["importance"]
    )
    op.create_index(
        "ix_kpi_definitions_sector_key_version",
        "kpi_definitions",
        ["sector", "key", "calculator_version"],
    )

    with op.batch_alter_table("kpi_values") as batch:
        batch.add_column(sa.Column("organization_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("workspace_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("asset_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("mission_id", sa.String(36), nullable=True))
        batch.add_column(
            sa.Column("status", sa.String(20), nullable=False, server_default="UNKNOWN")
        )
        batch.add_column(
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column(
                "measured_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
        batch.add_column(
            sa.Column("source", sa.String(160), nullable=False, server_default="legacy")
        )
        batch.add_column(
            sa.Column(
                "algorithm_version",
                sa.String(40),
                nullable=False,
                server_default="legacy-1",
            )
        )
        batch.add_column(
            sa.Column("provenance_json", sa.Text(), nullable=False, server_default="{}")
        )
        batch.add_column(
            sa.Column("is_baseline", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.create_foreign_key(
            "fk_kpi_values_organization_id_companies",
            "companies",
            ["organization_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_kpi_values_workspace_id_accounts",
            "accounts",
            ["workspace_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_kpi_values_asset_id_assets",
            "assets",
            ["asset_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_kpi_values_mission_id_acquisitions",
            "acquisitions",
            ["mission_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_check_constraint(
            "ck_kpi_value_status",
            "status IN ('GOOD', 'WATCH', 'WARNING', 'CRITICAL', 'UNKNOWN')",
        )
        batch.create_check_constraint(
            "ck_kpi_value_confidence", "confidence >= 0 AND confidence <= 1"
        )

    bind.execute(
        sa.text(
            """
            UPDATE kpi_values
               SET workspace_id = account_id,
                   organization_id = (
                       SELECT accounts.organization_id
                         FROM accounts
                        WHERE accounts.id = kpi_values.account_id
                   ),
                   asset_id = (
                       SELECT assets.id
                         FROM assets
                        WHERE assets.legacy_source = 'site'
                          AND assets.legacy_source_id = kpi_values.site_id
                        LIMIT 1
                   ),
                   measured_at = recorded_at
            """
        )
    )
    for column in (
        "organization_id",
        "workspace_id",
        "asset_id",
        "mission_id",
        "status",
        "measured_at",
        "is_baseline",
    ):
        op.create_index(f"ix_kpi_values_{column}", "kpi_values", [column])
    op.create_index(
        "ix_kpi_values_asset_definition_measured",
        "kpi_values",
        ["asset_id", "kpi_definition_id", "measured_at"],
    )

    op.create_table(
        "observations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=True),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column("mission_id", sa.String(36), nullable=True),
        sa.Column("dataset_id", sa.String(36), nullable=True),
        sa.Column("observation_type", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="INFO"),
        sa.Column("geometry_geojson", sa.Text(), nullable=True),
        sa.Column("value_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("numeric_value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(160), nullable=False),
        sa.Column("algorithm_key", sa.String(160), nullable=False),
        sa.Column("algorithm_version", sa.String(40), nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "validation_status",
            sa.String(30),
            nullable=False,
            server_default="UNVALIDATED",
        ),
        sa.Column("validated_by_user_id", sa.String(36), nullable=True),
        sa.Column("validated_at", sa.DateTime(), nullable=True),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
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
            "severity IN ('INFO', 'WATCH', 'WARNING', 'CRITICAL')",
            name="ck_observation_severity",
        ),
        sa.CheckConstraint(
            "validation_status IN ('UNVALIDATED', 'NEEDS_REVIEW', 'VALIDATED', 'REJECTED')",
            name="ck_observation_validation_status",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_observation_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["companies.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["accounts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["mission_id"], ["acquisitions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["validated_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "organization_id",
        "workspace_id",
        "asset_id",
        "mission_id",
        "dataset_id",
        "observation_type",
        "severity",
        "validation_status",
        "detected_at",
    ):
        op.create_index(f"ix_observations_{column}", "observations", [column])
    op.create_index(
        "ix_observations_asset_detected",
        "observations",
        ["asset_id", "detected_at"],
    )
    op.create_index(
        "ix_observations_asset_validation_severity",
        "observations",
        ["asset_id", "validation_status", "severity"],
    )

    op.create_table(
        "intelligence_actions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=True),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column("source_observation_id", sa.String(36), nullable=True),
        sa.Column("source_rule_key", sa.String(160), nullable=False),
        sa.Column("source_rule_version", sa.String(40), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="OPEN"),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("assigned_to_user_id", sa.String(36), nullable=True),
        sa.Column("recommended_catalog_item_id", sa.String(50), nullable=True),
        sa.Column("recommendation_refs_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("outcome_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("deduplication_key", sa.String(240), nullable=False),
        sa.Column("lifecycle_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("completed_by_user_id", sa.String(36), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
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
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT', 'CRITICAL')",
            name="ck_intelligence_action_priority",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'IN_PROGRESS', 'COMPLETED', 'DISMISSED', 'CANCELLED')",
            name="ck_intelligence_action_status",
        ),
        sa.CheckConstraint(
            "lifecycle_version > 0", name="ck_intelligence_action_version"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["companies.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["accounts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_observation_id"], ["observations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["recommended_catalog_item_id"], ["catalog_items.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["completed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "deduplication_key",
            name="uq_intelligence_action_org_deduplication",
        ),
    )
    for column in (
        "organization_id",
        "workspace_id",
        "asset_id",
        "source_observation_id",
        "priority",
        "status",
        "due_date",
        "assigned_to_user_id",
        "recommended_catalog_item_id",
    ):
        op.create_index(
            f"ix_intelligence_actions_{column}", "intelligence_actions", [column]
        )
    op.create_index(
        "ix_intelligence_actions_asset_status_priority",
        "intelligence_actions",
        ["asset_id", "status", "priority"],
    )


def downgrade() -> None:
    op.drop_table("intelligence_actions")
    op.drop_table("observations")

    for name in (
        "ix_kpi_values_asset_definition_measured",
        "ix_kpi_values_is_baseline",
        "ix_kpi_values_measured_at",
        "ix_kpi_values_status",
        "ix_kpi_values_mission_id",
        "ix_kpi_values_asset_id",
        "ix_kpi_values_workspace_id",
        "ix_kpi_values_organization_id",
    ):
        op.drop_index(name, table_name="kpi_values")
    with op.batch_alter_table("kpi_values") as batch:
        batch.drop_constraint("ck_kpi_value_confidence", type_="check")
        batch.drop_constraint("ck_kpi_value_status", type_="check")
        batch.drop_constraint(
            "fk_kpi_values_mission_id_acquisitions", type_="foreignkey"
        )
        batch.drop_constraint("fk_kpi_values_asset_id_assets", type_="foreignkey")
        batch.drop_constraint(
            "fk_kpi_values_workspace_id_accounts", type_="foreignkey"
        )
        batch.drop_constraint(
            "fk_kpi_values_organization_id_companies", type_="foreignkey"
        )
        for column in (
            "is_baseline",
            "provenance_json",
            "algorithm_version",
            "source",
            "measured_at",
            "confidence",
            "status",
            "mission_id",
            "asset_id",
            "workspace_id",
            "organization_id",
        ):
            batch.drop_column(column)

    op.drop_index(
        "ix_kpi_definitions_sector_key_version", table_name="kpi_definitions"
    )
    op.drop_index("ix_kpi_definitions_importance", table_name="kpi_definitions")
    with op.batch_alter_table("kpi_definitions") as batch:
        batch.drop_constraint("ck_kpi_definition_importance", type_="check")
        for column in (
            "updated_at",
            "status_policy_json",
            "display_format_json",
            "importance",
            "calculator_version",
            "calculator",
            "name",
        ):
            batch.drop_column(column)
