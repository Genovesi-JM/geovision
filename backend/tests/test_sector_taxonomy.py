import pytest
from pydantic import TypeAdapter, ValidationError

from app.modules.analytics.domain import KpiDefinitionSpec
from app.modules.assets.domain import normalize_sector
from app.modules.catalog.services import normalize_sector as normalize_catalog_sector
from app.modules.organizations.schemas import WorkspaceCreate
from app.routers.admin import CompanyCreate, ProductCreate, SiteCreate
from app.sector_taxonomy import (
    PUBLIC_SECTOR_DEFINITIONS,
    PUBLIC_SECTOR_IDS,
    asset_sector_for_public,
    capability_sector_for_public,
    normalize_capability_modules,
    normalize_public_sector,
    normalize_public_sector_values,
    normalize_sector_focus,
    public_sector_for_asset,
)
from app.services.risk_engine import RiskEngine, RiskEvidenceError, SectorType


def test_public_sector_taxonomy_is_exact_ordered_and_unique():
    assert PUBLIC_SECTOR_IDS == (
        "agriculture",
        "construction_infrastructure",
        "environment",
        "mining",
        "industry_energy_utilities",
        "ports_logistics",
    )
    assert len({item.slug_pt for item in PUBLIC_SECTOR_DEFINITIONS}) == 6
    assert [item.label_pt for item in PUBLIC_SECTOR_DEFINITIONS] == [
        "Agricultura & Pecuária",
        "Construção & Infraestruturas",
        "Ambiente",
        "Mineração",
        "Indústria, Energia & Utilities",
        "Portos & Logística",
    ]


def test_legacy_aliases_converge_without_collapsing_mining_industry_or_ports():
    assert normalize_public_sector("agro") == "agriculture"
    assert normalize_public_sector("construction") == "construction_infrastructure"
    assert normalize_public_sector("ambiental") == "environment"
    assert normalize_public_sector("mining") == "mining"
    assert normalize_public_sector("industry") == "industry_energy_utilities"
    assert normalize_public_sector("ports_industrial") == "ports_logistics"
    assert normalize_public_sector("portos") == "ports_logistics"
    assert normalize_public_sector("Agricultura & Pecuária") == "agriculture"
    assert (
        normalize_public_sector("Construção & Infraestruturas")
        == "construction_infrastructure"
    )
    assert normalize_public_sector("Ambiente") == "environment"
    assert normalize_public_sector("Mineração") == "mining"
    assert (
        normalize_public_sector("Indústria, Energia & Utilities")
        == "industry_energy_utilities"
    )
    assert normalize_public_sector("Portos & Logística") == "ports_logistics"
    assert normalize_sector_focus("Indústria, Energia & Utilities") == (
        "industry_energy_utilities"
    )
    assert normalize_sector_focus("agro,agriculture,industry,ports") == (
        "agriculture,industry_energy_utilities,ports_logistics"
    )
    assert (
        normalize_sector_focus("Agricultura & Pecuária,Indústria, Energia & Utilities")
        == "agriculture,industry_energy_utilities"
    )
    assert normalize_public_sector_values(
        ["Agricultura & Pecuária", "Indústria, Energia & Utilities"]
    ) == ["agriculture", "industry_energy_utilities"]
    assert normalize_public_sector_values("ports,???") == [
        "ports_logistics",
        "???",
    ]
    assert normalize_public_sector_values("Indústria, Energia & Utilities,ports") == [
        "industry_energy_utilities",
        "ports_logistics",
    ]
    assert normalize_public_sector_values("Indústria, Energia & Utilities,???") == [
        "industry_energy_utilities",
        "???",
    ]
    assert normalize_sector_focus("Indústria, Energia e Utilities") == (
        "industry_energy_utilities"
    )
    unknowns = ",".join(f"future_{index}" for index in range(1_000))
    assert len(normalize_public_sector_values(unknowns)) == 1_000


def test_public_and_asset_taxonomies_have_an_explicit_round_trip():
    for public_id in PUBLIC_SECTOR_IDS:
        asset_sector = asset_sector_for_public(public_id)
        assert asset_sector is not None
        assert public_sector_for_asset(asset_sector) == public_id
        assert normalize_sector(public_id) == asset_sector
        assert normalize_catalog_sector(public_id) == asset_sector

    assert normalize_sector("PORTS_INDUSTRIAL") == "PORTS_LOGISTICS"
    assert normalize_sector("ports-and-logistics") == "PORTS_LOGISTICS"
    assert normalize_sector("construction-and-infrastructure") == "INFRASTRUCTURE"
    assert normalize_sector("industry") == "INDUSTRY_ENERGY_UTILITIES"
    assert normalize_sector("mining") == "MINING"
    assert (
        KpiDefinitionSpec(
            sector="ports_industrial",
            key="test",
            name="Test",
            calculator="test.calculator",
            version="1",
        ).sector
        == "PORTS_LOGISTICS"
    )


def test_public_sectors_resolve_to_distinct_capability_modules():
    assert [item.capability_sector for item in PUBLIC_SECTOR_DEFINITIONS] == [
        "agriculture",
        "infrastructure",
        "environmental",
        "mining",
        "industry_energy_utilities",
        "ports_logistics",
    ]
    assert [capability_sector_for_public(item) for item in PUBLIC_SECTOR_IDS] == [
        "agriculture",
        "infrastructure",
        "environmental",
        "mining",
        "industry_energy_utilities",
        "ports_logistics",
    ]
    assert normalize_capability_modules(
        ["assets", "construction", "environment", "ports_industrial", "assets"]
    ) == ["assets", "infrastructure", "environmental", "ports_logistics"]


def test_risk_transport_advertises_six_values_and_accepts_legacy_aliases():
    assert tuple(item.value for item in SectorType) == PUBLIC_SECTOR_IDS
    assert TypeAdapter(SectorType).json_schema()["enum"] == list(PUBLIC_SECTOR_IDS)
    assert SectorType("agro") is SectorType.AGRICULTURE
    assert SectorType("infrastructure") is SectorType.CONSTRUCTION_INFRASTRUCTURE
    assert SectorType("solar") is SectorType.INDUSTRY_ENERGY_UTILITIES
    assert SectorType("ports_industrial") is SectorType.PORTS_LOGISTICS


def test_risk_engine_uses_evidence_bounds_and_published_warning_boundaries():
    engine = RiskEngine()
    mining = {
        "tailings_level_pct": 70,
        "terrain_displacement_mm": 5,
        "esg_score": 90,
        "dust_concentration_ppm": 50,
        "water_quality_index": 69,
        "extraction_efficiency_pct": 79,
    }
    result = engine.assess("mine-1", SectorType.MINING, mining)
    assert {
        "mining_dust_warning",
        "mining_water_warning",
        "mining_efficiency_warning",
    } <= {rule.rule_id for rule in result.triggered_rules}

    with pytest.raises(RiskEvidenceError):
        engine.assess(
            "mine-1",
            SectorType.MINING,
            {**mining, "tailings_level_pct": -1},
        )

    infrastructure = {
        "structural_health_index": 94,
        "timeline_delay_days": 0,
        "budget_overrun_pct": 0,
        "safety_incidents_30d": 0,
        "material_quality_pass_rate": 94,
    }
    infra_result = engine.assess(
        "infra-1",
        SectorType.CONSTRUCTION_INFRASTRUCTURE,
        infrastructure,
    )
    assert "infra_material_warning" in {
        rule.rule_id for rule in infra_result.triggered_rules
    }
    with pytest.raises(RiskEvidenceError):
        engine.assess(
            "infra-1",
            SectorType.CONSTRUCTION_INFRASTRUCTURE,
            {**infrastructure, "safety_incidents_30d": -1},
        )


def test_admin_writes_persist_only_canonical_public_sector_ids():
    company = CompanyCreate(
        name="Taxonomy test",
        email="taxonomy@example.com",
        sectors=["agro", "infrastructure", "ports"],
    )
    assert company.sectors == [
        "agriculture",
        "construction_infrastructure",
        "ports_logistics",
    ]
    assert SiteCreate(name="Mine", sector="quarry").sector == "mining"
    assert ProductCreate(name="Power", sectors=["solar"]).sectors == [
        "industry_energy_utilities"
    ]

    with pytest.raises(ValidationError):
        SiteCreate(name="Unknown", sector="not-a-geovision-sector")
    with pytest.raises(ValidationError):
        WorkspaceCreate(name="Too many", sectors=["agriculture"] * 7)
    with pytest.raises(ValidationError):
        ProductCreate(name="Too many", sectors=["agriculture"] * 7)
