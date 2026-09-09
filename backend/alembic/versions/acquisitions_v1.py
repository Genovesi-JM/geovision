"""Add provider-neutral acquisitions and map legacy missions/inspections.

Revision ID: acquisitions_v1
Revises: fulfilment_jobs_v1
"""

from __future__ import annotations

import json
import uuid

from alembic import op
import sqlalchemy as sa


revision = "acquisitions_v1"
down_revision = "fulfilment_jobs_v1"
branch_labels = None
depends_on = None


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _loads(value, fallback):
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError):
        return fallback
    return parsed if isinstance(parsed, type(fallback)) else fallback


def _legacy_id(source: str, source_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"geovision:acquisition:{source}:{source_id}"))


def _legacy_state(value: object) -> str:
    return {
        "draft": "DRAFT",
        "planned": "PLANNED",
        "approved": "PLANNED",
        "approved_for_provider_handoff": "PLANNED",
        "scheduled": "SCHEDULED",
        "in_progress": "IN_PROGRESS",
        "captured": "DATA_CAPTURED",
        "uploaded": "DATA_CAPTURED",
        "processing": "PROCESSING",
        "completed": "COMPLETED",
        "cancelled": "CANCELLED",
        "failed": "FAILED",
        "needs_reflight": "NEEDS_REFLIGHT",
    }.get(str(value or "").strip().lower(), "DRAFT")


def _provider(value: object) -> str | None:
    if not value:
        return None
    import re

    normalized = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    return normalized[:80] or None


def _capture_area(boundary_json: object) -> str | None:
    points = _loads(boundary_json, [])
    coordinates: list[list[float]] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        latitude = point.get("lat", point.get("latitude"))
        longitude = point.get("lng", point.get("longitude"))
        try:
            longitude_value = float(longitude)
            latitude_value = float(latitude)
        except (TypeError, ValueError):
            continue
        if -180 <= longitude_value <= 180 and -90 <= latitude_value <= 90:
            coordinates.append([longitude_value, latitude_value])
    if len(coordinates) < 3:
        return None
    if coordinates[0] != coordinates[-1]:
        coordinates.append(coordinates[0])
    return _dumps({"type": "Polygon", "coordinates": [coordinates]})


def _insert_acquisition(connection, values: dict) -> None:
    connection.execute(
        sa.text(
            """
            INSERT INTO acquisitions
                (id, acquisition_number, organization_id, workspace_id,
                 asset_id, order_id, fulfilment_job_id, acquisition_type,
                 title, description, state, provider_code,
                 provider_reference, provenance_json, metadata_json,
                 output_refs_json, scheduled_start, scheduled_end, started_at,
                 captured_at, completed_at, lifecycle_version, legacy_source,
                 legacy_source_id, created_by_user_id, updated_by_user_id,
                 created_at, updated_at)
            VALUES
                (:id, :acquisition_number, :organization_id, :workspace_id,
                 :asset_id, NULL, NULL, :acquisition_type, :title,
                 :description, :state, :provider_code, :provider_reference,
                 :provenance_json, :metadata_json, :output_refs_json, NULL,
                 NULL, :started_at, :captured_at, :completed_at, 1,
                 :legacy_source, :legacy_source_id, :created_by_user_id,
                 :updated_by_user_id, :created_at, :updated_at)
            """
        ),
        values,
    )


def _backfill_drone_missions() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT dm.id, dm.company_id, dm.site_id, dm.aircraft_id,
                   dm.created_by, dm.name, dm.mission_type, dm.status,
                   dm.altitude_m, dm.speed_mps, dm.front_overlap_percent,
                   dm.side_overlap_percent, dm.boundary_json, dm.route_json,
                   dm.checklist_json, dm.provider_reference,
                   dm.created_at, dm.updated_at, da.provider,
                   da.connection_mode, a.id AS asset_id,
                   a.workspace_id AS workspace_id
            FROM drone_missions dm
            LEFT JOIN drone_aircraft da ON da.id = dm.aircraft_id
            JOIN assets a
              ON a.legacy_source = 'site'
             AND a.legacy_source_id = dm.site_id
            ORDER BY dm.created_at, dm.id
            """
        )
    ).mappings()
    for row in rows:
        acquisition_id = _legacy_id("drone_mission", row["id"])
        state = _legacy_state(row["status"])
        _insert_acquisition(
            connection,
            {
                "id": acquisition_id,
                "acquisition_number": f"GVAQ-LEGACY-{acquisition_id[:12].upper()}",
                "organization_id": row["company_id"],
                "workspace_id": row["workspace_id"],
                "asset_id": row["asset_id"],
                "acquisition_type": "DRONE",
                "title": row["name"],
                "description": None,
                "state": state,
                "provider_code": _provider(row["provider"]),
                "provider_reference": row["provider_reference"],
                "provenance_json": _dumps(
                    {"source": "legacy_drone_mission", "source_id": row["id"]}
                ),
                "metadata_json": _dumps(
                    {
                        "legacy_mission_type": row["mission_type"],
                        "route": _loads(row["route_json"], []),
                    }
                ),
                "output_refs_json": "[]",
                "started_at": row["created_at"] if state == "IN_PROGRESS" else None,
                "captured_at": (
                    row["updated_at"]
                    if state in {"DATA_CAPTURED", "PROCESSING", "COMPLETED"}
                    else None
                ),
                "completed_at": row["updated_at"] if state == "COMPLETED" else None,
                "legacy_source": "drone_mission",
                "legacy_source_id": row["id"],
                "created_by_user_id": row["created_by"],
                "updated_by_user_id": row["created_by"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            },
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO drone_acquisition_details
                    (acquisition_id, aircraft_id, payload_reference,
                     operator_user_id, contractor_id,
                     mission_requirements_json, capture_area_geojson,
                     flight_metadata_json, reflight_of_acquisition_id,
                     reflight_reason, created_at, updated_at)
                VALUES
                    (:acquisition_id, :aircraft_id, NULL, NULL, NULL,
                     :mission_requirements_json, :capture_area_geojson,
                     :flight_metadata_json, NULL, :reflight_reason,
                     :created_at, :updated_at)
                """
            ),
            {
                "acquisition_id": acquisition_id,
                "aircraft_id": row["aircraft_id"],
                "mission_requirements_json": _dumps(
                    {
                        "mission_type": row["mission_type"],
                        "altitude_m": row["altitude_m"],
                        "speed_mps": float(row["speed_mps"]),
                        "front_overlap_percent": row["front_overlap_percent"],
                        "side_overlap_percent": row["side_overlap_percent"],
                        "safety_checklist": _loads(row["checklist_json"], {}),
                    }
                ),
                "capture_area_geojson": _capture_area(row["boundary_json"]),
                "flight_metadata_json": _dumps(
                    {
                        "legacy_route": _loads(row["route_json"], []),
                        "connection_mode": row["connection_mode"],
                    }
                ),
                "reflight_reason": (
                    "Mapped from legacy needs_reflight state"
                    if state == "NEEDS_REFLIGHT"
                    else None
                ),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            },
        )


def _backfill_inspections() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT ai.id, ai.company_id, ai.asset_id AS legacy_asset_id,
                   ai.site_id, ai.inspected_by, ai.category, ai.result,
                   ai.notes, ai.checklist_json, ai.photos_json, ai.latitude,
                   ai.longitude, ai.created_at,
                   COALESCE(ia.id, direct_asset.id, site_asset.id) AS asset_id,
                   COALESCE(ia.workspace_id, direct_asset.workspace_id,
                            site_asset.workspace_id) AS workspace_id
            FROM asset_inspections ai
            LEFT JOIN assets ia
              ON ia.legacy_source = 'iot_asset'
             AND ia.legacy_source_id = ai.asset_id
            LEFT JOIN assets direct_asset ON direct_asset.id = ai.asset_id
            LEFT JOIN assets site_asset
              ON site_asset.legacy_source = 'site'
             AND site_asset.legacy_source_id = ai.site_id
            WHERE COALESCE(ia.id, direct_asset.id, site_asset.id) IS NOT NULL
            ORDER BY ai.created_at, ai.id
            """
        )
    ).mappings()
    for row in rows:
        acquisition_id = _legacy_id("asset_inspection", row["id"])
        _insert_acquisition(
            connection,
            {
                "id": acquisition_id,
                "acquisition_number": f"GVAQ-LEGACY-{acquisition_id[:12].upper()}",
                "organization_id": row["company_id"],
                "workspace_id": row["workspace_id"],
                "asset_id": row["asset_id"],
                "acquisition_type": "MANUAL_INSPECTION",
                "title": f"{str(row['category']).replace('_', ' ').title()} inspection",
                "description": row["notes"],
                "state": "COMPLETED",
                "provider_code": "geovision_manual",
                "provider_reference": None,
                "provenance_json": _dumps(
                    {"source": "legacy_asset_inspection", "source_id": row["id"]}
                ),
                "metadata_json": _dumps(
                    {
                        "category": row["category"],
                        "result": row["result"],
                        "checklist": _loads(row["checklist_json"], {}),
                        "location": {
                            "latitude": row["latitude"],
                            "longitude": row["longitude"],
                        },
                    }
                ),
                "output_refs_json": _dumps(
                    [
                        {"type": "photo", "reference": reference}
                        for reference in _loads(row["photos_json"], [])
                    ]
                ),
                "started_at": row["created_at"],
                "captured_at": row["created_at"],
                "completed_at": row["created_at"],
                "legacy_source": "asset_inspection",
                "legacy_source_id": row["id"],
                "created_by_user_id": row["inspected_by"],
                "updated_by_user_id": row["inspected_by"],
                "created_at": row["created_at"],
                "updated_at": row["created_at"],
            },
        )


def upgrade() -> None:
    op.create_table(
        "acquisitions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("acquisition_number", sa.String(length=40), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=True),
        sa.Column("fulfilment_job_id", sa.String(length=36), nullable=True),
        sa.Column("acquisition_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("state", sa.String(length=30), nullable=False, server_default="DRAFT"),
        sa.Column("provider_code", sa.String(length=80), nullable=True),
        sa.Column("provider_reference", sa.String(length=200), nullable=True),
        sa.Column("provenance_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("output_refs_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("scheduled_start", sa.DateTime(), nullable=True),
        sa.Column("scheduled_end", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("captured_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("lifecycle_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("legacy_source", sa.String(length=50), nullable=True),
        sa.Column("legacy_source_id", sa.String(length=100), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "acquisition_type IN ('DRONE', 'SATELLITE', 'IOT', "
            "'MANUAL_INSPECTION', 'THIRD_PARTY_DATA')",
            name="ck_acquisition_type",
        ),
        sa.CheckConstraint(
            "state IN ('DRAFT', 'PLANNED', 'SCHEDULED', 'IN_PROGRESS', "
            "'DATA_CAPTURED', 'PROCESSING', 'COMPLETED', 'CANCELLED', "
            "'FAILED', 'NEEDS_REFLIGHT')",
            name="ck_acquisition_state",
        ),
        sa.CheckConstraint(
            "scheduled_end IS NULL OR scheduled_start IS NULL OR scheduled_end > scheduled_start",
            name="ck_acquisition_schedule_window",
        ),
        sa.CheckConstraint("lifecycle_version > 0", name="ck_acquisition_version"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["fulfilment_job_id"], ["fulfilment_jobs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["companies.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("acquisition_number", name="uq_acquisition_number"),
        sa.UniqueConstraint(
            "legacy_source", "legacy_source_id", name="uq_acquisition_legacy_source_id"
        ),
    )
    for column in (
        "acquisition_number",
        "organization_id",
        "workspace_id",
        "asset_id",
        "order_id",
        "fulfilment_job_id",
        "acquisition_type",
        "state",
        "provider_code",
    ):
        op.create_index(
            f"ix_acquisitions_{column}",
            "acquisitions",
            [column],
            unique=column == "acquisition_number",
        )
    op.create_index(
        "ix_acquisitions_asset_chronology",
        "acquisitions",
        ["asset_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "drone_acquisition_details",
        sa.Column("acquisition_id", sa.String(length=36), nullable=False),
        sa.Column("aircraft_id", sa.String(length=36), nullable=True),
        sa.Column("payload_reference", sa.String(length=200), nullable=True),
        sa.Column("operator_user_id", sa.String(length=36), nullable=True),
        sa.Column("contractor_id", sa.String(length=36), nullable=True),
        sa.Column(
            "mission_requirements_json", sa.Text(), nullable=False, server_default="{}"
        ),
        sa.Column("capture_area_geojson", sa.Text(), nullable=True),
        sa.Column("flight_metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("reflight_of_acquisition_id", sa.String(length=36), nullable=True),
        sa.Column("reflight_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "NOT (operator_user_id IS NOT NULL AND contractor_id IS NOT NULL)",
            name="ck_drone_acquisition_single_operator",
        ),
        sa.CheckConstraint(
            "reflight_of_acquisition_id IS NULL OR reflight_of_acquisition_id <> acquisition_id",
            name="ck_drone_acquisition_not_own_reflight",
        ),
        sa.ForeignKeyConstraint(
            ["acquisition_id"], ["acquisitions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["aircraft_id"], ["drone_aircraft.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["contractor_id"], ["operations_contractors.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["operator_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["reflight_of_acquisition_id"], ["acquisitions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("acquisition_id"),
    )
    for column in ("aircraft_id", "contractor_id", "reflight_of_acquisition_id"):
        op.create_index(
            f"ix_drone_acquisition_details_{column}",
            "drone_acquisition_details",
            [column],
            unique=False,
        )

    _backfill_drone_missions()
    _backfill_inspections()


def downgrade() -> None:
    for column in ("reflight_of_acquisition_id", "contractor_id", "aircraft_id"):
        op.drop_index(
            f"ix_drone_acquisition_details_{column}",
            table_name="drone_acquisition_details",
        )
    op.drop_table("drone_acquisition_details")
    op.drop_index("ix_acquisitions_asset_chronology", table_name="acquisitions")
    for column in (
        "provider_code",
        "state",
        "acquisition_type",
        "fulfilment_job_id",
        "order_id",
        "asset_id",
        "workspace_id",
        "organization_id",
        "acquisition_number",
    ):
        op.drop_index(f"ix_acquisitions_{column}", table_name="acquisitions")
    op.drop_table("acquisitions")
