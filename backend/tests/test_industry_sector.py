from datetime import datetime, timezone

from app.models import KpiDefinition
from app.modules.analytics.domain import EvaluationContext, calculator_registry
from app.sectors.industry import definition
from app.sectors.industry.domain import KPI_DEFINITIONS, SECTOR
from app.sectors.services import sync_enabled_sector_definitions


def test_industry_kpi_definition_is_registered_and_bootstrapped(db_session):
    assert definition.enabled_by_default is True
    assert definition.name == "industry_energy_utilities"

    registrations = calculator_registry.registrations(SECTOR)
    assert [item.definition.key for item in registrations] == [
        "equipment_attention_count"
    ]

    sync_enabled_sector_definitions(db_session)
    rows = (
        db_session.query(KpiDefinition)
        .filter(
            KpiDefinition.sector == SECTOR,
            KpiDefinition.key == "equipment_attention_count",
        )
        .all()
    )
    assert len(rows) == 1
    assert rows[0].calculator == "industry.equipment_attention_count"
    assert rows[0].calculator_version == KPI_DEFINITIONS[0].version
    assert rows[0].is_active is True

    sync_enabled_sector_definitions(db_session)
    assert (
        db_session.query(KpiDefinition)
        .filter(
            KpiDefinition.sector == SECTOR,
            KpiDefinition.key == "equipment_attention_count",
        )
        .count()
        == 1
    )


def test_industry_calculator_counts_only_explicit_traceable_observations():
    calculator = calculator_registry.resolve(SECTOR, "equipment_attention_count")
    first_at = datetime(2026, 9, 9, 8, tzinfo=timezone.utc)
    second_at = datetime(2026, 9, 10, 9, tzinfo=timezone.utc)
    result = calculator.calculate(
        EvaluationContext(
            asset_id="facility-1",
            sector=SECTOR,
            measured_at=second_at,
            metadata={
                "equipment_observations": (
                    {
                        "observation_id": "observation-1",
                        "source_reference": "inspection-log/42",
                        "requires_attention": True,
                        "recorded_at": first_at,
                        "confidence": 0.92,
                    },
                    {
                        "observation_id": "observation-2",
                        "source_reference": "inspection-log/43",
                        "requires_attention": False,
                        "recorded_at": second_at,
                        "confidence": 0.84,
                    },
                )
            },
        )
    )

    assert result is not None
    assert result.value == 1
    assert result.measured_at == second_at.replace(tzinfo=None)
    assert result.confidence == 0.84
    assert result.source == "industry.recorded_equipment_observations"
    assert result.provenance["observation_ids"] == [
        "observation-1",
        "observation-2",
    ]


def test_industry_calculator_does_not_infer_zero_without_valid_evidence():
    calculator = calculator_registry.resolve(SECTOR, "equipment_attention_count")
    measured_at = datetime(2026, 9, 10, 9)

    assert (
        calculator.calculate(EvaluationContext("facility-1", SECTOR, measured_at))
        is None
    )
    assert (
        calculator.calculate(
            EvaluationContext(
                "facility-1",
                SECTOR,
                measured_at,
                measurements={"equipment_attention_count": 0},
            )
        )
        is None
    )
    assert (
        calculator.calculate(
            EvaluationContext(
                "facility-1",
                SECTOR,
                measured_at,
                metadata={
                    "equipment_observations": (
                        {
                            "observation_id": "observation-1",
                            "source_reference": "inspection-log/42",
                            "requires_attention": False,
                            "recorded_at": measured_at,
                            "confidence": 0.9,
                        },
                        {
                            "observation_id": "observation-1",
                            "source_reference": "inspection-log/42",
                            "requires_attention": True,
                            "recorded_at": measured_at,
                            "confidence": 0.9,
                        },
                    )
                },
            )
        )
        is None
    )
