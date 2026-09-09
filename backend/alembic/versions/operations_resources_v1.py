"""Add private suppliers, contractors, capabilities, and assignments.

Revision ID: operations_resources_v1
Revises: commercial_order_lifecycle_v1
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from alembic import op
import sqlalchemy as sa


revision = "operations_resources_v1"
down_revision = "commercial_order_lifecycle_v1"
branch_labels = None
depends_on = None


_CAPABILITIES = (
    ("RGB", "RGB imaging", "SENSOR"),
    ("RTK", "RTK positioning", "POSITIONING"),
    ("MULTISPECTRAL", "Multispectral imaging", "SENSOR"),
    ("THERMAL", "Thermal imaging", "SENSOR"),
    ("LIDAR", "LiDAR acquisition", "SENSOR"),
    ("AGRICULTURE", "Agriculture expertise", "SECTOR"),
    ("INFRASTRUCTURE", "Infrastructure expertise", "SECTOR"),
    ("ENVIRONMENTAL", "Environmental expertise", "SECTOR"),
    ("MINING", "Mining expertise", "SECTOR"),
    ("PORTS_INDUSTRIAL", "Ports and industrial expertise", "SECTOR"),
    ("AGRONOMY", "Agronomy", "PROFESSIONAL"),
    ("IOT_INSTALLATION", "IoT installation", "PROFESSIONAL"),
    ("FIELD_TECHNICIAN", "Field technician", "PROFESSIONAL"),
    ("SURVEYING", "Surveying", "PROFESSIONAL"),
    ("DATA_ANALYSIS", "Data analysis", "PROFESSIONAL"),
)


def _capability_id(code: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"geovision:capability:{code}"))


def upgrade() -> None:
    with op.batch_alter_table("procurement_suppliers") as batch:
        batch.add_column(sa.Column("country_code", sa.String(length=2), nullable=True))
        batch.add_column(sa.Column("region", sa.String(length=120), nullable=True))
        batch.add_column(
            sa.Column("service_area_json", sa.Text(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column("capabilities_json", sa.Text(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column("certifications_json", sa.Text(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column("insurance_json", sa.Text(), nullable=False, server_default="{}")
        )
        batch.add_column(
            sa.Column("document_refs_json", sa.Text(), nullable=False, server_default="[]")
        )
        batch.add_column(sa.Column("quality_score", sa.Numeric(5, 2), nullable=True))
        batch.add_column(sa.Column("last_reviewed_at", sa.DateTime(), nullable=True))
        batch.create_check_constraint(
            "ck_procurement_supplier_quality_score",
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 100)",
        )
    op.create_index(
        "ix_procurement_suppliers_country_code",
        "procurement_suppliers",
        ["country_code"],
        unique=False,
    )
    op.create_index(
        "ix_procurement_suppliers_region",
        "procurement_suppliers",
        ["region"],
        unique=False,
    )

    op.create_table(
        "operational_capabilities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_operational_capability_code"),
    )
    op.create_index(
        "ix_operational_capabilities_code",
        "operational_capabilities",
        ["code"],
        unique=True,
    )
    op.create_index(
        "ix_operational_capabilities_category",
        "operational_capabilities",
        ["category"],
        unique=False,
    )
    op.create_index(
        "ix_operational_capabilities_is_active",
        "operational_capabilities",
        ["is_active"],
        unique=False,
    )

    op.create_table(
        "operations_contractors",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("legal_name", sa.String(length=200), nullable=True),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "availability", sa.String(length=20), nullable=False, server_default="AVAILABLE"
        ),
        sa.Column("contact_email", sa.String(length=320), nullable=True),
        sa.Column("contact_phone", sa.String(length=50), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("service_area_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("certifications_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("insurance_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("equipment_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("document_refs_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("quality_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("internal_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'ON_HOLD', 'INACTIVE', 'BLOCKED')",
            name="ck_operations_contractor_status",
        ),
        sa.CheckConstraint(
            "availability IN ('AVAILABLE', 'LIMITED', 'UNAVAILABLE')",
            name="ck_operations_contractor_availability",
        ),
        sa.CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 100)",
            name="ck_operations_contractor_quality_score",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_operations_contractor_code"),
        sa.UniqueConstraint("user_id", name="uq_operations_contractor_user"),
    )
    for column in (
        "code",
        "user_id",
        "resource_type",
        "status",
        "availability",
        "country_code",
        "region",
    ):
        op.create_index(
            f"ix_operations_contractors_{column}",
            "operations_contractors",
            [column],
            unique=column in {"code", "user_id"},
        )

    op.create_table(
        "contractor_capabilities",
        sa.Column("contractor_id", sa.String(length=36), nullable=False),
        sa.Column("capability_id", sa.String(length=36), nullable=False),
        sa.Column(
            "proficiency", sa.String(length=20), nullable=False, server_default="QUALIFIED"
        ),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "proficiency IN ('BASIC', 'QUALIFIED', 'EXPERT')",
            name="ck_contractor_capability_proficiency",
        ),
        sa.ForeignKeyConstraint(
            ["capability_id"], ["operational_capabilities.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["contractor_id"], ["operations_contractors.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("contractor_id", "capability_id"),
    )
    op.create_index(
        "ix_contractor_capabilities_capability_id",
        "contractor_capabilities",
        ["capability_id"],
        unique=False,
    )

    op.create_table(
        "contractor_assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("assignment_number", sa.String(length=40), nullable=False),
        sa.Column("contractor_id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=True),
        sa.Column("fulfilment_job_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="OFFERED"),
        sa.Column("location_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("window_start", sa.DateTime(), nullable=True),
        sa.Column("window_end", sa.DateTime(), nullable=True),
        sa.Column("requirements_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("upload_area_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("required_documents_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("agreed_cost_amount", sa.Integer(), nullable=True),
        sa.Column("cost_currency", sa.String(length=5), nullable=True),
        sa.Column("internal_notes", sa.Text(), nullable=True),
        sa.Column("assigned_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("lifecycle_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('OFFERED', 'ACCEPTED', 'DECLINED', 'ACTIVE', 'COMPLETED', 'CANCELLED')",
            name="ck_contractor_assignment_status",
        ),
        sa.CheckConstraint(
            "agreed_cost_amount IS NULL OR agreed_cost_amount >= 0",
            name="ck_contractor_assignment_cost_nonnegative",
        ),
        sa.CheckConstraint(
            "lifecycle_version > 0", name="ck_contractor_assignment_lifecycle_version"
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["contractor_id"], ["operations_contractors.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assignment_number", name="uq_contractor_assignment_number"),
    )
    for column in (
        "assignment_number",
        "contractor_id",
        "order_id",
        "fulfilment_job_id",
        "status",
    ):
        op.create_index(
            f"ix_contractor_assignments_{column}",
            "contractor_assignments",
            [column],
            unique=column == "assignment_number",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    capabilities = sa.table(
        "operational_capabilities",
        sa.column("id", sa.String()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("category", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("is_active", sa.Boolean()),
        sa.column("metadata_json", sa.Text()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    op.bulk_insert(
        capabilities,
        [
            {
                "id": _capability_id(code),
                "code": code,
                "name": name,
                "category": category,
                "description": None,
                "is_active": True,
                "metadata_json": "{}",
                "created_at": now,
                "updated_at": now,
            }
            for code, name, category in _CAPABILITIES
        ],
    )


def downgrade() -> None:
    for column in (
        "status",
        "fulfilment_job_id",
        "order_id",
        "contractor_id",
        "assignment_number",
    ):
        op.drop_index(
            f"ix_contractor_assignments_{column}", table_name="contractor_assignments"
        )
    op.drop_table("contractor_assignments")
    op.drop_index(
        "ix_contractor_capabilities_capability_id", table_name="contractor_capabilities"
    )
    op.drop_table("contractor_capabilities")
    for column in (
        "region",
        "country_code",
        "availability",
        "status",
        "resource_type",
        "user_id",
        "code",
    ):
        op.drop_index(
            f"ix_operations_contractors_{column}", table_name="operations_contractors"
        )
    op.drop_table("operations_contractors")
    op.drop_index(
        "ix_operational_capabilities_is_active", table_name="operational_capabilities"
    )
    op.drop_index(
        "ix_operational_capabilities_category", table_name="operational_capabilities"
    )
    op.drop_index(
        "ix_operational_capabilities_code", table_name="operational_capabilities"
    )
    op.drop_table("operational_capabilities")

    op.drop_index(
        "ix_procurement_suppliers_region", table_name="procurement_suppliers"
    )
    op.drop_index(
        "ix_procurement_suppliers_country_code", table_name="procurement_suppliers"
    )
    with op.batch_alter_table("procurement_suppliers") as batch:
        batch.drop_constraint("ck_procurement_supplier_quality_score", type_="check")
        batch.drop_column("last_reviewed_at")
        batch.drop_column("quality_score")
        batch.drop_column("document_refs_json")
        batch.drop_column("insurance_json")
        batch.drop_column("certifications_json")
        batch.drop_column("capabilities_json")
        batch.drop_column("service_area_json")
        batch.drop_column("region")
        batch.drop_column("country_code")
