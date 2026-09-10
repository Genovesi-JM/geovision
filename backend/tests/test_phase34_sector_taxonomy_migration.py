from __future__ import annotations

from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa


_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "phase34_sector_taxonomy_v1.py"
)
_SPEC = spec_from_file_location("phase34_sector_taxonomy_v1", _MIGRATION_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MIGRATION = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MIGRATION)


def test_public_csv_preserves_order_unknowns_and_dedupes_known_collisions():
    value = " odd value ,agro,AGRICULTURE,industry,mining,ports_industrial,???"

    assert _MIGRATION._normalize_csv(value, _MIGRATION._PUBLIC_BY_KEY) == (
        " odd value ,agriculture,industry_energy_utilities,mining,ports_logistics,???"
    )
    assert (
        _MIGRATION._normalize_csv("ports,???", _MIGRATION._PUBLIC_BY_KEY)
        == "ports_logistics,???"
    )
    assert (
        _MIGRATION._normalize_csv(
            "Indústria, Energia & Utilities,???", _MIGRATION._PUBLIC_BY_KEY
        )
        == "industry_energy_utilities,???"
    )


def test_public_json_preserves_malformed_and_non_string_entries():
    assert (
        _MIGRATION._normalize_json_list("not-json", _MIGRATION._PUBLIC_BY_KEY)
        == "not-json"
    )
    assert (
        _MIGRATION._normalize_json_list(
            '["environmental","environment",7,{"legacy":true},"custom"]',
            _MIGRATION._PUBLIC_BY_KEY,
        )
        == '["environment",7,{"legacy":true},"custom"]'
    )


def test_portuguese_labels_and_slugs_converge_to_the_exact_six_public_ids():
    assert _MIGRATION._normalize_csv(
        "agricultura-pecuaria,construcao-infraestruturas,ambiente,mineracao,"
        "industria-energia-utilities,portos-logistica",
        _MIGRATION._PUBLIC_BY_KEY,
    ) == (
        "agriculture,construction_infrastructure,environment,mining,"
        "industry_energy_utilities,ports_logistics"
    )
    assert (
        _MIGRATION._normalize_csv(
            "Indústria, Energia & Utilities", _MIGRATION._PUBLIC_BY_KEY
        )
        == "industry_energy_utilities"
    )
    assert (
        _MIGRATION._normalize_csv(
            "Agricultura & Pecuária,Indústria, Energia & Utilities",
            _MIGRATION._PUBLIC_BY_KEY,
        )
        == "agriculture,industry_energy_utilities"
    )
    assert _MIGRATION._normalize_json_list(
        '["Agricultura & Pecuária","Construção & Infraestruturas","Ambiente",'
        '"Mineração","Indústria, Energia & Utilities","Portos & Logística"]',
        _MIGRATION._PUBLIC_BY_KEY,
    ) == (
        '["agriculture","construction_infrastructure","environment","mining",'
        '"industry_energy_utilities","ports_logistics"]'
    )


def test_company_json_flattens_legacy_comma_packed_sector_focus():
    assert (
        _MIGRATION._normalize_json_csv_list(
            '["agro,industry","PORTS_INDUSTRIAL","custom",7]',
            _MIGRATION._PUBLIC_BY_KEY,
        )
        == '["agriculture","industry_energy_utilities","ports_logistics","custom",7]'
    )
    assert (
        _MIGRATION._normalize_json_csv_list(
            '["Indústria, Energia & Utilities","Portos & Logística"]',
            _MIGRATION._PUBLIC_BY_KEY,
        )
        == '["industry_energy_utilities","ports_logistics"]'
    )
    assert (
        _MIGRATION._normalize_json_csv_list(
            '["Agricultura & Pecuária,Indústria, Energia & Utilities"]',
            _MIGRATION._PUBLIC_BY_KEY,
        )
        == '["agriculture","industry_energy_utilities"]'
    )


def test_company_json_preserves_unknown_extension_values_containing_commas():
    assert (
        _MIGRATION._normalize_json_csv_list(
            '["Future, Special"]', _MIGRATION._PUBLIC_BY_KEY
        )
        == '["Future, Special"]'
    )
    assert (
        _MIGRATION._normalize_json_csv_list(
            '["custom,value",7]', _MIGRATION._PUBLIC_BY_KEY
        )
        == '["custom,value",7]'
    )
    assert (
        _MIGRATION._normalize_json_csv_list(
            '["agro,custom"]', _MIGRATION._PUBLIC_BY_KEY
        )
        == '["agro,custom"]'
    )


def test_technical_values_keep_mining_separate_from_industry_and_ports():
    values = (
        '["industry","industrial","energy","utilities","mining","ports_industrial"]'
    )

    assert (
        _MIGRATION._normalize_json_list(values, _MIGRATION._TECHNICAL_BY_KEY)
        == '["INDUSTRY_ENERGY_UTILITIES","MINING","PORTS_LOGISTICS"]'
    )


def test_public_scalars_and_module_codes_use_distinct_canonical_dialects():
    assert (
        _MIGRATION._normalize_scalar("infrastructure", _MIGRATION._PUBLIC_BY_KEY)
        == "construction_infrastructure"
    )
    assert (
        _MIGRATION._normalize_scalar("ENVIRONMENTAL", _MIGRATION._PUBLIC_BY_KEY)
        == "environment"
    )
    assert (
        _MIGRATION._normalize_json_list(
            '["construction","environment","assets"]',
            _MIGRATION._MODULE_BY_KEY,
        )
        == '["infrastructure","environmental","assets"]'
    )


def test_port_product_rows_gain_both_new_sector_identities():
    public = _MIGRATION._normalize_json_list(
        '["ports_industrial"]', _MIGRATION._PUBLIC_BY_KEY
    )
    technical = _MIGRATION._normalize_json_list(
        '["PORTS_INDUSTRIAL"]', _MIGRATION._TECHNICAL_BY_KEY
    )

    assert (
        _MIGRATION._ensure_json_members(
            public, ("industry_energy_utilities", "ports_logistics")
        )
        == '["ports_logistics","industry_energy_utilities"]'
    )
    assert (
        _MIGRATION._ensure_json_members(
            technical, ("INDUSTRY_ENERGY_UTILITIES", "PORTS_LOGISTICS")
        )
        == '["PORTS_LOGISTICS","INDUSTRY_ENERGY_UTILITIES"]'
    )


def test_only_owned_combined_products_are_eligible_for_sector_expansion():
    assert _MIGRATION._LEGACY_COMBINED_FIRST_PARTY_PRODUCT_IDS == {
        "prod_ports_visual_inspection",
        "prod_ports_thermal_inspection",
        "prod_ports_3d_mapping",
        "prod_ports_sensor_installation",
        "prod_ports_monitoring_plan",
        "prod_ports_specialist_review",
    }
    assert (
        "prod_ports_customer_extension"
        not in _MIGRATION._LEGACY_COMBINED_FIRST_PARTY_PRODUCT_IDS
    )


def test_operations_expertise_declares_six_canonical_codes():
    assert tuple(_MIGRATION._SECTOR_CAPABILITIES) == (
        "AGRICULTURE",
        "INFRASTRUCTURE",
        "ENVIRONMENTAL",
        "MINING",
        "INDUSTRY_ENERGY_UTILITIES",
        "PORTS_LOGISTICS",
    )


def test_operations_expertise_upgrade_preserves_links_and_downgrades_exactly():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    capabilities = sa.Table(
        "operational_capabilities",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("code", sa.String, unique=True),
        sa.Column("name", sa.String),
        sa.Column("category", sa.String),
        sa.Column("description", sa.Text),
        sa.Column("is_active", sa.Boolean),
        sa.Column("metadata_json", sa.Text),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )
    links = sa.Table(
        "contractor_capabilities",
        metadata,
        sa.Column("contractor_id", sa.String, primary_key=True),
        sa.Column("capability_id", sa.String, primary_key=True),
        sa.Column("proficiency", sa.String),
        sa.Column("verified_at", sa.DateTime),
        sa.Column("expires_at", sa.DateTime),
        sa.Column("notes", sa.Text),
    )
    metadata.create_all(engine)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    historical = (
        ("AGRICULTURE", "Agriculture expertise"),
        ("INFRASTRUCTURE", "Infrastructure expertise"),
        ("ENVIRONMENTAL", "Environmental expertise"),
        ("MINING", "Mining expertise"),
        ("PORTS_INDUSTRIAL", "Ports and industrial expertise"),
    )

    with engine.begin() as connection:
        for code, name in historical:
            connection.execute(
                capabilities.insert().values(
                    id=_MIGRATION._capability_id(code),
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
        legacy_ports_id = _MIGRATION._capability_id("PORTS_INDUSTRIAL")
        connection.execute(
            links.insert().values(
                contractor_id="contractor-1",
                capability_id=legacy_ports_id,
                proficiency="EXPERT",
            )
        )
        _MIGRATION.op = Operations(MigrationContext.configure(connection))

        _MIGRATION.upgrade()

        codes = set(
            connection.execute(
                sa.select(capabilities.c.code).where(
                    capabilities.c.category == "SECTOR"
                )
            ).scalars()
        )
        assert codes == set(_MIGRATION._SECTOR_CAPABILITIES)
        assert connection.execute(sa.select(links.c.capability_id)).scalar_one() == (
            legacy_ports_id
        )
        assert (
            connection.execute(
                sa.select(capabilities.c.code).where(
                    capabilities.c.id == legacy_ports_id
                )
            ).scalar_one()
            == "PORTS_LOGISTICS"
        )

        _MIGRATION.downgrade()

        restored_codes = set(
            connection.execute(sa.select(capabilities.c.code)).scalars()
        )
        assert restored_codes == {code for code, _ in historical}
        assert connection.execute(sa.select(links.c.capability_id)).scalar_one() == (
            legacy_ports_id
        )


def test_operations_expertise_merges_equivalent_duplicate_and_preserves_later_edits():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    capabilities = sa.Table(
        "operational_capabilities",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("code", sa.String, unique=True),
        sa.Column("name", sa.String),
        sa.Column("category", sa.String),
        sa.Column("description", sa.Text),
        sa.Column("is_active", sa.Boolean),
        sa.Column("metadata_json", sa.Text),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )
    links = sa.Table(
        "contractor_capabilities",
        metadata,
        sa.Column("contractor_id", sa.String, primary_key=True),
        sa.Column("capability_id", sa.String, primary_key=True),
        sa.Column("proficiency", sa.String),
        sa.Column("verified_at", sa.DateTime),
        sa.Column("expires_at", sa.DateTime),
        sa.Column("notes", sa.Text),
    )
    metadata.create_all(engine)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    legacy_id = _MIGRATION._capability_id("PORTS_INDUSTRIAL")
    canonical_id = _MIGRATION._capability_id("PORTS_LOGISTICS")
    original_capabilities = (
        (legacy_id, "PORTS_INDUSTRIAL", "Historical combined expertise"),
        (canonical_id, "PORTS_LOGISTICS", "Existing ports expertise"),
    )
    original_links = (
        ("contractor-legacy", legacy_id, "EXPERT", "legacy only"),
        ("contractor-both", legacy_id, "QUALIFIED", "canonical original"),
        ("contractor-both", canonical_id, "QUALIFIED", "canonical original"),
    )

    with engine.begin() as connection:
        for row_id, code, name in original_capabilities:
            connection.execute(
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
        for contractor_id, capability_id, proficiency, notes in original_links:
            connection.execute(
                links.insert().values(
                    contractor_id=contractor_id,
                    capability_id=capability_id,
                    proficiency=proficiency,
                    verified_at=now,
                    notes=notes,
                )
            )
        _MIGRATION.op = Operations(MigrationContext.configure(connection))

        _MIGRATION.upgrade()

        assert set(connection.execute(sa.select(capabilities.c.code)).scalars()) == set(
            _MIGRATION._SECTOR_CAPABILITIES
        )
        assert set(
            connection.execute(
                sa.select(
                    links.c.contractor_id,
                    links.c.capability_id,
                    links.c.proficiency,
                    links.c.notes,
                )
            )
        ) == {
            ("contractor-legacy", canonical_id, "EXPERT", "legacy only"),
            ("contractor-both", canonical_id, "QUALIFIED", "canonical original"),
        }

        connection.execute(
            links.update()
            .where(
                links.c.contractor_id == "contractor-legacy",
                links.c.capability_id == canonical_id,
            )
            .values(notes="edited after upgrade")
        )

        _MIGRATION.downgrade()

        assert set(connection.execute(sa.select(capabilities.c.code)).scalars()) == {
            code for _, code, _ in original_capabilities
        }
        assert set(
            connection.execute(
                sa.select(
                    links.c.contractor_id,
                    links.c.capability_id,
                    links.c.proficiency,
                    links.c.notes,
                )
            )
        ) == {
            ("contractor-legacy", legacy_id, "EXPERT", "edited after upgrade"),
            ("contractor-both", legacy_id, "QUALIFIED", "canonical original"),
            ("contractor-both", canonical_id, "QUALIFIED", "canonical original"),
        }

        connection.execute(
            links.update()
            .where(
                links.c.contractor_id == "contractor-both",
                links.c.capability_id == legacy_id,
            )
            .values(proficiency="BASIC")
        )
        with pytest.raises(RuntimeError, match="contractor Ports capabilities"):
            _MIGRATION.upgrade()
        connection.exec_driver_sql(f"DROP TABLE IF EXISTS {_MIGRATION._BACKUP_TABLE}")
        connection.execute(
            links.update()
            .where(
                links.c.contractor_id == "contractor-both",
                links.c.capability_id == legacy_id,
            )
            .values(proficiency="QUALIFIED")
        )

        connection.execute(
            capabilities.update()
            .where(capabilities.c.id == canonical_id)
            .values(is_active=False)
        )
        with pytest.raises(RuntimeError, match="activation requires manual review"):
            _MIGRATION.upgrade()
        connection.exec_driver_sql(f"DROP TABLE IF EXISTS {_MIGRATION._BACKUP_TABLE}")
        connection.execute(
            capabilities.update()
            .where(capabilities.c.id == canonical_id)
            .values(is_active=True, category="OTHER")
        )
        with pytest.raises(RuntimeError, match="code collision requires manual review"):
            _MIGRATION.upgrade()


def test_scalar_normalization_preserves_unknown_values_exactly():
    assert (
        _MIGRATION._normalize_scalar(
            "  Future/Special Sector  ", _MIGRATION._TECHNICAL_BY_KEY
        )
        == "  Future/Special Sector  "
    )
    assert (
        _MIGRATION._normalize_scalar("ports_industrial", _MIGRATION._TECHNICAL_BY_KEY)
        == "PORTS_LOGISTICS"
    )
