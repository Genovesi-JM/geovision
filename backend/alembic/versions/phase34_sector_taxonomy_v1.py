"""Converge persisted sector identifiers on the six-sector taxonomy.

Revision ID: phase34_sector_taxonomy_v1
Revises: service_request_journey_v1

Known legacy identifiers are normalized while unknown or malformed values are
left byte-for-byte intact.  Changed values are recorded so downgrade can
restore the exact pre-migration representation without guessing which legacy
alias produced a canonical value.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
import uuid

from alembic import op
import sqlalchemy as sa


revision = "phase34_sector_taxonomy_v1"
down_revision = "service_request_journey_v1"
branch_labels = None
depends_on = None


_BACKUP_TABLE = "phase34_sector_taxonomy_backup"

_PUBLIC_BY_KEY = {
    "agriculture": "agriculture",
    "agro": "agriculture",
    "agropecuaria": "agriculture",
    "agricultura": "agriculture",
    "agricultura_e_pecuaria": "agriculture",
    "agricultura_pecuaria": "agriculture",
    "agriculture_livestock": "agriculture",
    "livestock": "agriculture",
    "construction": "construction_infrastructure",
    "construction_and_infrastructure": "construction_infrastructure",
    "construction_infrastructure": "construction_infrastructure",
    "construcao_e_infraestruturas": "construction_infrastructure",
    "construcao_infraestrutura": "construction_infrastructure",
    "construcao_infraestruturas": "construction_infrastructure",
    "infrastructure": "construction_infrastructure",
    "infrastructures": "construction_infrastructure",
    "ambiente": "environment",
    "ambiental": "environment",
    "environment": "environment",
    "environmental": "environment",
    "mine": "mining",
    "mines": "mining",
    "mineracao": "mining",
    "mining": "mining",
    "quarry": "mining",
    "energy": "industry_energy_utilities",
    "energia": "industry_energy_utilities",
    "industrial": "industry_energy_utilities",
    "industria": "industry_energy_utilities",
    "industria_e_energia_utilities": "industry_energy_utilities",
    "industria_energia_e_utilities": "industry_energy_utilities",
    "industria_energia_utilities": "industry_energy_utilities",
    "industry": "industry_energy_utilities",
    "industry_energy": "industry_energy_utilities",
    "industry_energy_utilities": "industry_energy_utilities",
    "solar": "industry_energy_utilities",
    "utilities": "industry_energy_utilities",
    "logistics": "ports_logistics",
    "logistica": "ports_logistics",
    "port": "ports_logistics",
    "ports": "ports_logistics",
    "ports_and_logistics": "ports_logistics",
    "ports_industrial": "ports_logistics",
    "ports_logistics": "ports_logistics",
    "portos": "ports_logistics",
    "portos_e_logistica": "ports_logistics",
    "portos_logistica": "ports_logistics",
}

_TECHNICAL_BY_KEY = {
    key: {
        "agriculture": "AGRICULTURE",
        "construction_infrastructure": "INFRASTRUCTURE",
        "environment": "ENVIRONMENTAL",
        "mining": "MINING",
        "industry_energy_utilities": "INDUSTRY_ENERGY_UTILITIES",
        "ports_logistics": "PORTS_LOGISTICS",
    }[public_id]
    for key, public_id in _PUBLIC_BY_KEY.items()
}

_MODULE_BY_KEY = {
    key: {
        "agriculture": "agriculture",
        "construction_infrastructure": "infrastructure",
        "environment": "environmental",
        "mining": "mining",
        "industry_energy_utilities": "industry_energy_utilities",
        "ports_logistics": "ports_logistics",
    }[public_id]
    for key, public_id in _PUBLIC_BY_KEY.items()
}

_PUBLIC_COLUMNS = (
    ("accounts", "sector_focus", "csv"),
    ("companies", "sectors", "json_csv"),
    ("sites", "sector", "scalar"),
    ("risk_assessments", "sector", "scalar"),
    ("shop_products", "sectors_json", "json"),
)
_MODULE_COLUMNS = (("accounts", "modules_enabled", "json"),)
_TECHNICAL_COLUMNS = (
    ("assets", "sector", "scalar"),
    ("datasets", "sector", "scalar"),
    ("kpi_definitions", "sector", "scalar"),
    ("catalog_items", "sectors_json", "json"),
)

# These six first-party definitions were deliberately sold under the historical
# combined Ports/Industrial catalogue. Their stable IDs are known. Never infer
# sector applicability from an arbitrary customer or extension ID prefix.
_LEGACY_COMBINED_FIRST_PARTY_PRODUCT_IDS = frozenset(
    {
        "prod_ports_visual_inspection",
        "prod_ports_thermal_inspection",
        "prod_ports_3d_mapping",
        "prod_ports_sensor_installation",
        "prod_ports_monitoring_plan",
        "prod_ports_specialist_review",
    }
)

_SECTOR_CAPABILITIES = {
    "AGRICULTURE": "Agriculture expertise",
    "INFRASTRUCTURE": "Infrastructure expertise",
    "ENVIRONMENTAL": "Environmental expertise",
    "MINING": "Mining expertise",
    "INDUSTRY_ENERGY_UTILITIES": "Industry, energy and utilities expertise",
    "PORTS_LOGISTICS": "Ports and logistics expertise",
}


def _key(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore")
    return re.sub(r"[^a-z0-9]+", "_", ascii_value.decode().lower()).strip("_")


def _comma_phrase_key(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore")
    compact = re.sub(r"\s*,\s*", ",", ascii_value.decode().strip().lower())
    return re.sub(r"\s+", " ", compact)


_COMMA_BEARING_PUBLIC_LABEL_KEYS = frozenset(
    _comma_phrase_key(label)
    for label in (
        "Indústria, Energia & Utilities",
        "Indústria, Energia e Utilities",
        "Industry, Energy & Utilities",
    )
)
_MAX_COMMA_BEARING_LABEL_PARTS = max(
    label.count(",") + 1 for label in _COMMA_BEARING_PUBLIC_LABEL_KEYS
)


def _known(value: Any, mapping: dict[str, str]) -> tuple[Any, bool]:
    if not isinstance(value, str):
        return value, False
    normalized = mapping.get(_key(value))
    return (normalized, True) if normalized is not None else (value, False)


def _normalize_scalar(value: Any, mapping: dict[str, str]) -> Any:
    return _known(value, mapping)[0]


def _split_known_csv(
    value: str,
    mapping: dict[str, str],
) -> list[tuple[str, Any, bool]]:
    """Split CSV while treating known labels containing commas as one member."""

    parts = value.split(",")
    output: list[tuple[str, Any, bool]] = []
    index = 0
    while index < len(parts):
        match: tuple[str, Any, bool] | None = None
        matched_end = index + 1
        furthest_end = min(len(parts), index + _MAX_COMMA_BEARING_LABEL_PARTS)
        for end in range(furthest_end, index + 1, -1):
            candidate = ",".join(parts[index:end])
            if _comma_phrase_key(candidate) not in _COMMA_BEARING_PUBLIC_LABEL_KEYS:
                continue
            candidate_key = _key(candidate)
            normalized = mapping.get(candidate_key)
            if normalized is not None:
                match = (candidate, normalized, True)
                matched_end = end
                break
        if match is None:
            candidate = parts[index]
            normalized, is_known = _known(candidate, mapping)
            match = candidate, normalized, is_known
        output.append(match)
        index = matched_end
    return output


def _normalize_csv(value: Any, mapping: dict[str, str]) -> Any:
    if not isinstance(value, str):
        return value
    output: list[str] = []
    seen_known: set[str] = set()
    changed = False
    for original, normalized, is_known in _split_known_csv(value, mapping):
        if is_known and normalized in seen_known:
            changed = True
            continue
        if is_known:
            seen_known.add(normalized)
            changed = changed or normalized != original
        output.append(normalized)
    return ",".join(output) if changed else value


def _normalize_json_list(value: Any, mapping: dict[str, str]) -> Any:
    if not isinstance(value, str):
        return value
    try:
        items = json.loads(value)
    except (TypeError, ValueError):
        return value
    if not isinstance(items, list):
        return value

    output: list[Any] = []
    seen_known: set[str] = set()
    changed = False
    for item in items:
        normalized, is_known = _known(item, mapping)
        if is_known and normalized in seen_known:
            changed = True
            continue
        if is_known:
            seen_known.add(normalized)
            changed = changed or normalized != item
        output.append(normalized)
    if not changed:
        return value
    return json.dumps(output, ensure_ascii=False, separators=(",", ":"))


def _normalize_json_csv_list(value: Any, mapping: dict[str, str]) -> Any:
    """Normalize JSON lists, flattening legacy comma-packed string members."""

    if not isinstance(value, str):
        return value
    try:
        items = json.loads(value)
    except (TypeError, ValueError):
        return value
    if not isinstance(items, list):
        return value

    output: list[Any] = []
    seen_known: set[str] = set()
    changed = False
    for item in items:
        if isinstance(item, str):
            parsed_members = _split_known_csv(item, mapping)
            members = (
                parsed_members
                if len(parsed_members) == 1
                or all(member[2] for member in parsed_members)
                else [(item, item, False)]
            )
        else:
            members = [(str(item), item, False)]
        changed = changed or len(members) > 1
        for original, normalized, is_known in members:
            if is_known and normalized in seen_known:
                changed = True
                continue
            if is_known:
                seen_known.add(normalized)
                changed = changed or normalized != original
            output.append(normalized)
    if not changed:
        return value
    return json.dumps(output, ensure_ascii=False, separators=(",", ":"))


def _ensure_json_members(value: Any, required: tuple[str, ...]) -> Any:
    if not isinstance(value, str):
        return value
    try:
        items = json.loads(value)
    except (TypeError, ValueError):
        return value
    if not isinstance(items, list):
        return value
    output = list(items)
    for item in required:
        if item not in output:
            output.append(item)
    if output == items:
        return value
    return json.dumps(output, ensure_ascii=False, separators=(",", ":"))


def _transformer(kind: str, mapping: dict[str, str]) -> Callable[[Any], Any]:
    if kind == "csv":
        return lambda value: _normalize_csv(value, mapping)
    if kind == "json":
        return lambda value: _normalize_json_list(value, mapping)
    if kind == "json_csv":
        return lambda value: _normalize_json_csv_list(value, mapping)
    return lambda value: _normalize_scalar(value, mapping)


def _available_column(bind: sa.Connection, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {
        column["name"] for column in inspector.get_columns(table_name)
    }


def _migrate_column(
    bind: sa.Connection,
    backup: sa.Table,
    table_name: str,
    column_name: str,
    transform: Callable[[Any], Any],
    *,
    port_product_members: tuple[str, ...] = (),
) -> None:
    if not _available_column(bind, table_name, column_name):
        return
    table = sa.Table(table_name, sa.MetaData(), autoload_with=bind)
    if "id" not in table.c:
        return
    column = table.c[column_name]
    rows = bind.execute(sa.select(table.c.id, column)).mappings().all()
    for row in rows:
        original = row[column_name]
        migrated = transform(original)
        if (
            port_product_members
            and str(row["id"]) in _LEGACY_COMBINED_FIRST_PARTY_PRODUCT_IDS
        ):
            migrated = _ensure_json_members(migrated, port_product_members)
        if migrated == original:
            continue
        row_id = str(row["id"])
        bind.execute(
            backup.insert().values(
                table_name=table_name,
                row_id=row_id,
                column_name=column_name,
                original_value=original,
                migrated_value=migrated,
            )
        )
        bind.execute(
            table.update()
            .where(table.c.id == row["id"])
            .values({column_name: migrated})
        )


def _capability_id(code: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"geovision:capability:{code}"))


def _backup_change(
    bind: sa.Connection,
    backup: sa.Table,
    table: sa.Table,
    row_id: Any,
    column_name: str,
    original: Any,
    migrated: Any,
) -> None:
    bind.execute(
        backup.insert().values(
            table_name=table.name,
            row_id=str(row_id),
            column_name=column_name,
            original_value=original,
            migrated_value=migrated,
        )
    )
    bind.execute(
        table.update().where(table.c.id == row_id).values({column_name: migrated})
    )


def _row_snapshot(row: sa.RowMapping) -> str:
    def encode(value: Any) -> Any:
        if isinstance(value, datetime):
            return {"__phase34_datetime__": value.isoformat()}
        raise TypeError(f"Unsupported migration snapshot value: {type(value).__name__}")

    return json.dumps(
        dict(row),
        default=encode,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _restore_snapshot(value: str | None) -> dict[str, Any]:
    if value is None:
        return {}

    def decode(item: dict[str, Any]) -> Any:
        encoded = item.get("__phase34_datetime__")
        if len(item) == 1 and isinstance(encoded, str):
            return datetime.fromisoformat(encoded)
        return item

    restored = json.loads(value, object_hook=decode)
    return restored if isinstance(restored, dict) else {}


def _backup_row_snapshot(
    bind: sa.Connection,
    backup: sa.Table,
    *,
    table_name: str,
    row_id: str,
    marker: str,
    row: sa.RowMapping,
    migrated_value: str | None = None,
) -> None:
    bind.execute(
        backup.insert().values(
            table_name=table_name,
            row_id=row_id,
            column_name=marker,
            original_value=_row_snapshot(row),
            migrated_value=migrated_value,
        )
    )


def _link_payload(row: sa.RowMapping) -> dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if key not in {"contractor_id", "capability_id"}
    }


def _normalize_operational_capabilities(bind: sa.Connection, backup: sa.Table) -> None:
    if not _available_column(bind, "operational_capabilities", "code"):
        return
    capabilities = sa.Table(
        "operational_capabilities", sa.MetaData(), autoload_with=bind
    )
    rows = bind.execute(sa.select(capabilities)).mappings().all()
    by_code = {str(row["code"]): row for row in rows}
    reserved_codes = {*_SECTOR_CAPABILITIES, "PORTS_INDUSTRIAL"}
    category_conflicts = [
        str(row["code"])
        for row in rows
        if str(row["code"]) in reserved_codes and row["category"] != "SECTOR"
    ]
    if category_conflicts:
        raise RuntimeError(
            "Phase 34 sector capability code collision requires manual review: "
            + ", ".join(sorted(category_conflicts))
        )
    legacy_ports = by_code.get("PORTS_INDUSTRIAL")
    canonical_ports = by_code.get("PORTS_LOGISTICS")
    links = (
        sa.Table("contractor_capabilities", sa.MetaData(), autoload_with=bind)
        if _available_column(bind, "contractor_capabilities", "capability_id")
        else None
    )
    if legacy_ports is not None and canonical_ports is not None:
        if bool(legacy_ports["is_active"]) != bool(canonical_ports["is_active"]):
            raise RuntimeError(
                "Conflicting Ports capability activation requires manual review"
            )
        if links is not None:
            legacy_links = bind.execute(
                sa.select(links).where(links.c.capability_id == legacy_ports["id"])
            ).mappings()
            canonical_links = {
                str(row["contractor_id"]): row
                for row in bind.execute(
                    sa.select(links).where(
                        links.c.capability_id == canonical_ports["id"]
                    )
                ).mappings()
            }
            for legacy_link in legacy_links:
                canonical_link = canonical_links.get(str(legacy_link["contractor_id"]))
                if canonical_link is not None and _link_payload(
                    legacy_link
                ) != _link_payload(canonical_link):
                    raise RuntimeError(
                        "Conflicting contractor Ports capabilities require manual review"
                    )
    if legacy_ports is not None and canonical_ports is None:
        _backup_change(
            bind,
            backup,
            capabilities,
            legacy_ports["id"],
            "code",
            "PORTS_INDUSTRIAL",
            "PORTS_LOGISTICS",
        )
        if legacy_ports["name"] != _SECTOR_CAPABILITIES["PORTS_LOGISTICS"]:
            _backup_change(
                bind,
                backup,
                capabilities,
                legacy_ports["id"],
                "name",
                legacy_ports["name"],
                _SECTOR_CAPABILITIES["PORTS_LOGISTICS"],
            )
        canonical_ports = dict(legacy_ports)
        canonical_ports["code"] = "PORTS_LOGISTICS"
        by_code.pop("PORTS_INDUSTRIAL", None)
        by_code["PORTS_LOGISTICS"] = canonical_ports

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for code, name in _SECTOR_CAPABILITIES.items():
        if code in by_code:
            continue
        row_id = _capability_id(code)
        bind.execute(
            capabilities.insert().values(
                id=row_id,
                code=code,
                name=name,
                category="SECTOR",
                description=None,
                is_active=True,
                metadata_json="{}",
                created_at=now,
                updated_at=now,
            )
        )
        bind.execute(
            backup.insert().values(
                table_name="operational_capabilities",
                row_id=row_id,
                column_name="__inserted__",
                original_value=None,
                migrated_value=code,
            )
        )
        by_code[code] = {"id": row_id, "code": code}

    legacy_ports = by_code.get("PORTS_INDUSTRIAL")
    canonical_ports = by_code.get("PORTS_LOGISTICS")
    if legacy_ports is None or canonical_ports is None:
        return

    if links is not None:
        legacy_links = (
            bind.execute(
                sa.select(links).where(links.c.capability_id == legacy_ports["id"])
            )
            .mappings()
            .all()
        )
        for link in legacy_links:
            exists = (
                bind.execute(
                    sa.select(links).where(
                        links.c.contractor_id == link["contractor_id"],
                        links.c.capability_id == canonical_ports["id"],
                    )
                )
                .mappings()
                .one_or_none()
            )
            marker = "__deleted_link__" if exists else "__moved_link__"
            _backup_row_snapshot(
                bind,
                backup,
                table_name="contractor_capabilities",
                row_id=f"{link['contractor_id']}:{legacy_ports['id']}",
                marker=marker,
                row=link,
                migrated_value=str(canonical_ports["id"]),
            )
            if exists:
                bind.execute(
                    links.delete().where(
                        links.c.contractor_id == link["contractor_id"],
                        links.c.capability_id == legacy_ports["id"],
                    )
                )
            else:
                bind.execute(
                    links.update()
                    .where(
                        links.c.contractor_id == link["contractor_id"],
                        links.c.capability_id == legacy_ports["id"],
                    )
                    .values(capability_id=canonical_ports["id"])
                )

    _backup_row_snapshot(
        bind,
        backup,
        table_name="operational_capabilities",
        row_id=str(legacy_ports["id"]),
        marker="__deleted_capability__",
        row=legacy_ports,
        migrated_value=str(canonical_ports["id"]),
    )
    bind.execute(capabilities.delete().where(capabilities.c.id == legacy_ports["id"]))


def upgrade() -> None:
    op.create_table(
        _BACKUP_TABLE,
        sa.Column("table_name", sa.String(64), nullable=False),
        sa.Column("row_id", sa.String(255), nullable=False),
        sa.Column("column_name", sa.String(64), nullable=False),
        sa.Column("original_value", sa.Text(), nullable=True),
        sa.Column("migrated_value", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("table_name", "row_id", "column_name"),
    )
    bind = op.get_bind()
    backup = sa.Table(_BACKUP_TABLE, sa.MetaData(), autoload_with=bind)
    for table_name, column_name, kind in _PUBLIC_COLUMNS:
        _migrate_column(
            bind,
            backup,
            table_name,
            column_name,
            _transformer(kind, _PUBLIC_BY_KEY),
            port_product_members=(
                "industry_energy_utilities",
                "ports_logistics",
            )
            if table_name == "shop_products"
            else (),
        )
    for table_name, column_name, kind in _TECHNICAL_COLUMNS:
        _migrate_column(
            bind,
            backup,
            table_name,
            column_name,
            _transformer(kind, _TECHNICAL_BY_KEY),
            port_product_members=(
                "INDUSTRY_ENERGY_UTILITIES",
                "PORTS_LOGISTICS",
            )
            if table_name == "catalog_items"
            else (),
        )
    for table_name, column_name, kind in _MODULE_COLUMNS:
        _migrate_column(
            bind,
            backup,
            table_name,
            column_name,
            _transformer(kind, _MODULE_BY_KEY),
        )
    _normalize_operational_capabilities(bind, backup)


def downgrade() -> None:
    bind = op.get_bind()
    if _BACKUP_TABLE not in sa.inspect(bind).get_table_names():
        return
    backup = sa.Table(_BACKUP_TABLE, sa.MetaData(), autoload_with=bind)
    entries = bind.execute(sa.select(backup)).mappings().all()

    # A deployment may already have both the historical and canonical Ports
    # capability. Upgrade merges that duplicate row; recreate it before its
    # contractor links are restored.
    for entry in entries:
        if entry["column_name"] != "__deleted_capability__":
            continue
        if not _available_column(bind, entry["table_name"], "id"):
            continue
        table = sa.Table(entry["table_name"], sa.MetaData(), autoload_with=bind)
        exists = bind.execute(
            sa.select(table.c.id).where(table.c.id == entry["row_id"])
        ).first()
        if exists is None:
            bind.execute(
                table.insert().values(**_restore_snapshot(entry["original_value"]))
            )

    if _available_column(bind, "contractor_capabilities", "capability_id"):
        links = sa.Table("contractor_capabilities", sa.MetaData(), autoload_with=bind)
        for entry in entries:
            if entry["column_name"] not in {"__moved_link__", "__deleted_link__"}:
                continue
            original = _restore_snapshot(entry["original_value"])
            contractor_id = original.get("contractor_id")
            capability_id = original.get("capability_id")
            if not contractor_id or not capability_id:
                continue
            if entry["column_name"] == "__moved_link__":
                current = (
                    bind.execute(
                        sa.select(links).where(
                            links.c.contractor_id == contractor_id,
                            links.c.capability_id == entry["migrated_value"],
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                legacy_exists = bind.execute(
                    sa.select(links.c.contractor_id).where(
                        links.c.contractor_id == contractor_id,
                        links.c.capability_id == capability_id,
                    )
                ).first()
                if current is not None and legacy_exists is not None:
                    raise RuntimeError(
                        "Downgrade found conflicting post-upgrade Ports capability links"
                    )
                if current is not None:
                    bind.execute(
                        links.update()
                        .where(
                            links.c.contractor_id == contractor_id,
                            links.c.capability_id == entry["migrated_value"],
                        )
                        .values(capability_id=capability_id)
                    )
                    continue
            exists = bind.execute(
                sa.select(links.c.contractor_id).where(
                    links.c.contractor_id == contractor_id,
                    links.c.capability_id == capability_id,
                )
            ).first()
            if exists is None:
                bind.execute(links.insert().values(**original))

    for entry in entries:
        if entry["column_name"] != "__inserted__":
            continue
        if not _available_column(bind, entry["table_name"], "code"):
            continue
        table = sa.Table(entry["table_name"], sa.MetaData(), autoload_with=bind)
        linked = False
        if entry["table_name"] == "operational_capabilities" and _available_column(
            bind, "contractor_capabilities", "capability_id"
        ):
            links = sa.Table(
                "contractor_capabilities", sa.MetaData(), autoload_with=bind
            )
            linked = (
                bind.execute(
                    sa.select(links.c.capability_id).where(
                        links.c.capability_id == entry["row_id"]
                    )
                ).first()
                is not None
            )
        if not linked:
            bind.execute(
                table.delete()
                .where(table.c.id == entry["row_id"])
                .where(table.c.code == entry["migrated_value"])
            )
    for entry in entries:
        table_name = entry["table_name"]
        column_name = entry["column_name"]
        if column_name.startswith("__"):
            continue
        if not _available_column(bind, table_name, column_name):
            continue
        table = sa.Table(table_name, sa.MetaData(), autoload_with=bind)
        if "id" not in table.c:
            continue
        bind.execute(
            table.update()
            .where(table.c.id == entry["row_id"])
            .where(table.c[column_name] == entry["migrated_value"])
            .values({column_name: entry["original_value"]})
        )
    op.drop_table(_BACKUP_TABLE)
