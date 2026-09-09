"""Create the generic Asset model and optional PostGIS projection.

Revision ID: generic_assets_postgis_v1
Revises: organization_rbac_v1
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import uuid

from alembic import context, op
import sqlalchemy as sa


revision = "generic_assets_postgis_v1"
down_revision = "organization_rbac_v1"
branch_labels = None
depends_on = None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _identifier(value: object, default: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(value or default).strip())
    normalized = normalized.strip("_").upper()
    return normalized or default


def _sector(value: object) -> str:
    normalized = _identifier(value, "AGRICULTURE")
    return {
        "AGRO": "AGRICULTURE",
        "AGRICULTURE": "AGRICULTURE",
        "LIVESTOCK": "AGRICULTURE",
        "CONSTRUCTION": "INFRASTRUCTURE",
        "INFRASTRUCTURE": "INFRASTRUCTURE",
        "ENVIRONMENT": "ENVIRONMENTAL",
        "ENVIRONMENTAL": "ENVIRONMENTAL",
        "AMBIENTAL": "ENVIRONMENTAL",
        "MINING": "MINING",
        "INDUSTRY": "PORTS_INDUSTRIAL",
        "INDUSTRIAL": "PORTS_INDUSTRIAL",
        "PORTS": "PORTS_INDUSTRIAL",
    }.get(normalized, normalized)


def _asset_id(connection, source: str, source_id: str) -> str:
    exists = connection.execute(
        sa.text("SELECT 1 FROM assets WHERE id = :id"),
        {"id": source_id},
    ).first()
    if exists is None:
        return source_id
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"geovision:asset:{source}:{source_id}"))


def _workspace_id(connection, organization_id: str) -> str | None:
    row = connection.execute(
        sa.text(
            """
            SELECT id FROM accounts
            WHERE organization_id = :organization_id AND status = 'active'
            ORDER BY created_at, id
            LIMIT 1
            """
        ),
        {"organization_id": organization_id},
    ).first()
    return row[0] if row else None


def _point(latitude: object, longitude: object):
    if latitude is None or longitude is None:
        return None, (None, None, None, None), (None, None)
    latitude_value = float(latitude)
    longitude_value = float(longitude)
    if not -90 <= latitude_value <= 90 or not -180 <= longitude_value <= 180:
        return None, (None, None, None, None), (None, None)
    geometry = json.dumps(
        {"type": "Point", "coordinates": [longitude_value, latitude_value]},
        separators=(",", ":"),
        sort_keys=True,
    )
    return (
        geometry,
        (longitude_value, latitude_value, longitude_value, latitude_value),
        (latitude_value, longitude_value),
    )


def _insert_asset(connection, values: dict) -> None:
    connection.execute(
        sa.text(
            """
            INSERT INTO assets
                (id, organization_id, workspace_id, parent_asset_id, sector,
                 asset_type, name, description, status, external_reference,
                 location_label, geometry_geojson, bbox_min_x, bbox_min_y,
                 bbox_max_x, bbox_max_y, centroid_latitude,
                 centroid_longitude, metadata_json, legacy_source,
                 legacy_source_id, created_by_user_id, updated_by_user_id,
                 archived_by_user_id, archived_at, created_at, updated_at)
            VALUES
                (:id, :organization_id, :workspace_id, :parent_asset_id,
                 :sector, :asset_type, :name, :description, :status,
                 :external_reference, :location_label, :geometry_geojson,
                 :bbox_min_x, :bbox_min_y, :bbox_max_x, :bbox_max_y,
                 :centroid_latitude, :centroid_longitude, :metadata_json,
                 :legacy_source, :legacy_source_id, NULL, NULL, NULL, NULL,
                 :created_at, :updated_at)
            """
        ),
        values,
    )


def _backfill_legacy_assets() -> None:
    connection = op.get_bind()
    site_asset_ids: dict[str, str] = {}
    sites = connection.execute(
        sa.text(
            """
            SELECT id, company_id, name, description, country, province,
                   municipality, latitude, longitude, area_hectares, sector,
                   is_active, created_at, updated_at
            FROM sites
            ORDER BY created_at, id
            """
        )
    ).mappings()
    for site in sites:
        asset_id = _asset_id(connection, "site", site["id"])
        site_asset_ids[site["id"]] = asset_id
        geometry, bounds, center = _point(site["latitude"], site["longitude"])
        location = ", ".join(
            part
            for part in (site["municipality"], site["province"], site["country"])
            if part
        )
        _insert_asset(
            connection,
            {
                "id": asset_id,
                "organization_id": site["company_id"],
                "workspace_id": _workspace_id(connection, site["company_id"]),
                "parent_asset_id": None,
                "sector": _sector(site["sector"]),
                "asset_type": "SITE",
                "name": site["name"],
                "description": site["description"],
                "status": "active" if site["is_active"] else "inactive",
                "external_reference": None,
                "location_label": location or None,
                "geometry_geojson": geometry,
                "bbox_min_x": bounds[0],
                "bbox_min_y": bounds[1],
                "bbox_max_x": bounds[2],
                "bbox_max_y": bounds[3],
                "centroid_latitude": center[0],
                "centroid_longitude": center[1],
                "metadata_json": json.dumps(
                    {
                        "legacy": {
                            "source": "site",
                            "country": site["country"],
                            "province": site["province"],
                            "municipality": site["municipality"],
                            "area_hectares": (
                                float(site["area_hectares"])
                                if site["area_hectares"] is not None
                                else None
                            ),
                        }
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                "legacy_source": "site",
                "legacy_source_id": site["id"],
                "created_at": site["created_at"] or _now(),
                "updated_at": site["updated_at"] or site["created_at"] or _now(),
            },
        )

    iot_assets = connection.execute(
        sa.text(
            """
            SELECT id, company_id, site_id, name, asset_type,
                   external_reference, latitude, longitude, metadata_json,
                   created_at
            FROM iot_assets
            ORDER BY created_at, id
            """
        )
    ).mappings()
    for legacy in iot_assets:
        asset_id = _asset_id(connection, "iot_asset", legacy["id"])
        parent_asset_id = site_asset_ids.get(legacy["site_id"])
        parent = None
        if parent_asset_id:
            parent = connection.execute(
                sa.text(
                    "SELECT workspace_id, sector FROM assets WHERE id = :id"
                ),
                {"id": parent_asset_id},
            ).first()
        geometry, bounds, center = _point(legacy["latitude"], legacy["longitude"])
        try:
            metadata = json.loads(legacy["metadata_json"] or "{}")
        except (TypeError, ValueError):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        metadata["legacy"] = {
            "source": "iot_asset",
            "site_id": legacy["site_id"],
        }
        _insert_asset(
            connection,
            {
                "id": asset_id,
                "organization_id": legacy["company_id"],
                "workspace_id": (
                    parent[0]
                    if parent
                    else _workspace_id(connection, legacy["company_id"])
                ),
                "parent_asset_id": parent_asset_id,
                "sector": parent[1] if parent else "INFRASTRUCTURE",
                "asset_type": _identifier(legacy["asset_type"], "EQUIPMENT"),
                "name": legacy["name"],
                "description": None,
                "status": "active",
                "external_reference": legacy["external_reference"],
                "location_label": None,
                "geometry_geojson": geometry,
                "bbox_min_x": bounds[0],
                "bbox_min_y": bounds[1],
                "bbox_max_x": bounds[2],
                "bbox_max_y": bounds[3],
                "centroid_latitude": center[0],
                "centroid_longitude": center[1],
                "metadata_json": json.dumps(
                    metadata,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                "legacy_source": "iot_asset",
                "legacy_source_id": legacy["id"],
                "created_at": legacy["created_at"] or _now(),
                "updated_at": legacy["created_at"] or _now(),
            },
        )


def _enable_postgis_projection() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        """
        DO $geovision$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis') THEN
                BEGIN
                    CREATE EXTENSION postgis;
                EXCEPTION
                    WHEN insufficient_privilege OR undefined_file THEN
                        RAISE NOTICE 'PostGIS unavailable; retaining portable GeoJSON storage';
                END;
            END IF;
        END
        $geovision$;
        """
    )
    postgis_available = op.get_bind().execute(
        sa.text("SELECT 1 FROM pg_extension WHERE extname = 'postgis'")
    ).first()
    if postgis_available is None:
        return
    op.execute(
        """
        ALTER TABLE assets
        ADD COLUMN geometry geometry(Geometry, 4326)
        GENERATED ALWAYS AS (
            CASE
                WHEN geometry_geojson IS NULL THEN NULL
                ELSE ST_SetSRID(ST_GeomFromGeoJSON(geometry_geojson), 4326)
            END
        ) STORED
        """
    )
    op.execute(
        "CREATE INDEX ix_assets_geometry_gist ON assets USING GIST (geometry)"
    )


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError(
            "generic_assets_postgis_v1 requires an online migration for legacy asset backfill"
        )

    op.create_table(
        "assets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            sa.ForeignKey("accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "parent_asset_id",
            sa.String(length=36),
            sa.ForeignKey("assets.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("sector", sa.String(length=50), nullable=False),
        sa.Column("asset_type", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="active", nullable=False),
        sa.Column("external_reference", sa.String(length=200), nullable=True),
        sa.Column("location_label", sa.String(length=500), nullable=True),
        sa.Column("geometry_geojson", sa.Text(), nullable=True),
        sa.Column("bbox_min_x", sa.Float(), nullable=True),
        sa.Column("bbox_min_y", sa.Float(), nullable=True),
        sa.Column("bbox_max_x", sa.Float(), nullable=True),
        sa.Column("bbox_max_y", sa.Float(), nullable=True),
        sa.Column("centroid_latitude", sa.Float(), nullable=True),
        sa.Column("centroid_longitude", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("legacy_source", sa.String(length=40), nullable=True),
        sa.Column("legacy_source_id", sa.String(length=100), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "archived_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "legacy_source",
            "legacy_source_id",
            name="uq_assets_legacy_source_id",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'inactive', 'archived')",
            name="ck_assets_status",
        ),
        sa.CheckConstraint(
            "parent_asset_id IS NULL OR parent_asset_id <> id",
            name="ck_assets_not_own_parent",
        ),
        sa.CheckConstraint(
            "bbox_min_x IS NULL OR (bbox_min_x >= -180 AND bbox_min_x <= 180)",
            name="ck_assets_bbox_min_x",
        ),
        sa.CheckConstraint(
            "bbox_max_x IS NULL OR (bbox_max_x >= -180 AND bbox_max_x <= 180)",
            name="ck_assets_bbox_max_x",
        ),
        sa.CheckConstraint(
            "bbox_min_y IS NULL OR (bbox_min_y >= -90 AND bbox_min_y <= 90)",
            name="ck_assets_bbox_min_y",
        ),
        sa.CheckConstraint(
            "bbox_max_y IS NULL OR (bbox_max_y >= -90 AND bbox_max_y <= 90)",
            name="ck_assets_bbox_max_y",
        ),
    )
    op.create_index("ix_assets_organization_id", "assets", ["organization_id"])
    op.create_index("ix_assets_workspace_id", "assets", ["workspace_id"])
    op.create_index("ix_assets_parent_asset_id", "assets", ["parent_asset_id"])
    op.create_index("ix_assets_sector", "assets", ["sector"])
    op.create_index("ix_assets_asset_type", "assets", ["asset_type"])
    op.create_index("ix_assets_status", "assets", ["status"])
    op.create_index(
        "ix_assets_scope_type_status",
        "assets",
        ["organization_id", "workspace_id", "asset_type", "status"],
    )
    op.create_index(
        "ix_assets_scope_parent",
        "assets",
        ["organization_id", "workspace_id", "parent_asset_id"],
    )
    op.create_index(
        "ix_assets_bbox",
        "assets",
        ["bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y"],
    )
    _backfill_legacy_assets()
    _enable_postgis_projection()


def downgrade() -> None:
    op.drop_table("assets")
