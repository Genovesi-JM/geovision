from __future__ import annotations

from datetime import datetime, timedelta
import uuid

import pytest

from app.core.tokens import create_user_access_token
from app.models import Action, Asset, EventOutbox, User
from app.modules.actions.services import materialize_evaluation_actions
from app.modules.analytics.domain import (
    ActionRecommendation,
    CalculatorRegistry,
    EvaluationContext,
    HistoricalValue,
    KpiCalculation,
    KpiDefinitionSpec,
    KpiImportance,
    KpiStatus,
    ObservationProposal,
    ObservationSeverity,
    RuleOutcome,
    RuleRegistry,
    ValidationStatus,
    calculate_kpi_status,
    format_kpi_value,
    historical_comparison,
)
from app.modules.analytics.services import (
    evaluate_asset,
    record_kpi_value,
    record_observation,
)


def _user(db_session, prefix: str) -> User:
    user = User(
        email=f"{prefix}-{uuid.uuid4().hex}@example.com",
        role="cliente",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _headers(user: User, workspace_id: str | None = None) -> dict[str, str]:
    token = create_user_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        auth_generation=user.auth_generation,
    )
    headers = {"Authorization": f"Bearer {token}"}
    if workspace_id:
        headers["X-Workspace-ID"] = workspace_id
    return headers


def _workspace_asset(client, db_session, prefix: str = "intelligence"):
    owner = _user(db_session, f"{prefix}-owner")
    response = client.post(
        "/organizations",
        headers=_headers(owner),
        json={
            "name": f"{prefix}-{uuid.uuid4().hex[:8]}",
            "country": "Angola",
            "timezone": "Africa/Luanda",
            "workspace": {
                "name": f"{prefix} workspace",
                "customer_type": "business",
                "sector_focus": "agro",
            },
        },
    )
    assert response.status_code == 201, response.text
    organization = response.json()
    workspace_id = organization["workspaces"][0]["id"]
    headers = _headers(owner, workspace_id)
    response = client.post(
        "/assets",
        headers=headers,
        json={
            "sector": "AGRICULTURE",
            "asset_type": "FIELD",
            "name": f"{prefix} field",
            "geometry": {"type": "Point", "coordinates": [13.1, -8.9]},
        },
    )
    assert response.status_code == 201, response.text
    return owner, organization["id"], workspace_id, response.json(), headers


def test_status_policies_are_backend_owned_and_confidence_aware():
    higher = {
        "mode": "higher_is_better",
        "good_min": 80,
        "watch_min": 60,
        "warning_min": 40,
        "minimum_confidence": 0.6,
    }
    assert calculate_kpi_status(90, higher, confidence=0.9) is KpiStatus.GOOD
    assert calculate_kpi_status(70, higher, confidence=0.9) is KpiStatus.WATCH
    assert calculate_kpi_status(50, higher, confidence=0.9) is KpiStatus.WARNING
    assert calculate_kpi_status(20, higher, confidence=0.9) is KpiStatus.CRITICAL
    assert calculate_kpi_status(90, higher, confidence=0.4) is KpiStatus.UNKNOWN

    lower = {
        "mode": "lower_is_better",
        "good_max": 10,
        "watch_max": 20,
        "warning_max": 30,
    }
    assert calculate_kpi_status(5, lower) is KpiStatus.GOOD
    assert calculate_kpi_status(15, lower) is KpiStatus.WATCH
    assert calculate_kpi_status(25, lower) is KpiStatus.WARNING
    assert calculate_kpi_status(35, lower) is KpiStatus.CRITICAL
    assert calculate_kpi_status(None, lower) is KpiStatus.UNKNOWN
    assert (
        format_kpi_value(0.734, "%", {"multiplier": 100, "decimal_places": 1})
        == "73.4 %"
    )
    assert format_kpi_value(0.04, None, {"positive_prefix": "+"}) == "+0.04"


def test_calculator_and_rule_registries_select_latest_versions_without_core_edits():
    calculators = CalculatorRegistry()
    at = datetime(2026, 9, 10, 8)

    def calculation(version: int):
        return lambda _: KpiCalculation(
            value=version,
            measured_at=at,
            source="fixture",
            confidence=1,
            provenance={"version": version},
        )

    for version in ("1.0.0", "2.0.0"):
        calculators.register(
            KpiDefinitionSpec(
                sector="MINING",
                key="stockpile_change",
                name="Stockpile change",
                unit="m3",
                calculator="mining.stockpile_change",
                version=version,
                importance=KpiImportance.PRIMARY,
            ),
            calculation(int(version[0])),
        )
    latest = calculators.resolve("MINING", "stockpile_change")
    assert latest.definition.version == "2.0.0"
    assert latest.calculate(EvaluationContext("asset", "MINING", at)).value == 2
    assert (
        calculators.resolve("MINING", "stockpile_change", "1.0.0").definition.version
        == "1.0.0"
    )
    assert len(calculators.registrations("MINING")) == 1
    with pytest.raises(ValueError, match="already registered"):
        calculators.register(latest.definition, latest.calculate)

    rules = RuleRegistry()
    rules.register(
        sector="PORTS_LOGISTICS",
        key="port.anomaly",
        version="1.0.0",
        evaluate=lambda _context, _values: RuleOutcome(),
    )
    assert rules.registrations("PORTS_LOGISTICS")[0].key == "port.anomaly"
    assert rules.registrations("AGRICULTURE") == ()


@pytest.mark.parametrize(
    ("sector", "metric", "observation_type"),
    [
        ("AGRICULTURE", "crop_condition", "CROP_STRESS"),
        ("INFRASTRUCTURE", "construction_progress", "PROGRESS_VARIANCE"),
        ("MINING", "stockpile_change", "STOCKPILE_CHANGE"),
        (
            "INDUSTRY_ENERGY_UTILITIES",
            "asset_condition",
            "ASSET_ANOMALY",
        ),
        ("PORTS_LOGISTICS", "port_throughput", "PORT_ANOMALY"),
        ("ENVIRONMENTAL", "vegetation_change", "ENVIRONMENTAL_CHANGE"),
    ],
)
def test_same_core_accepts_every_supported_sector_registration(
    sector, metric, observation_type
):
    at = datetime(2026, 9, 10, 9)
    calculators = CalculatorRegistry()
    calculators.register(
        KpiDefinitionSpec(
            sector=sector,
            key=metric,
            name=metric.replace("_", " ").title(),
            calculator=f"{sector.lower()}.{metric}",
            version="1.0.0",
        ),
        lambda _: KpiCalculation(1, at, "validated-fixture", 0.9, {"fixture": True}),
    )
    rules = RuleRegistry()
    rules.register(
        sector=sector,
        key=f"{sector.lower()}.observation",
        version="1.0.0",
        evaluate=lambda context, _values: RuleOutcome(
            observations=(
                ObservationProposal(
                    key="finding",
                    observation_type=observation_type,
                    severity=ObservationSeverity.INFO,
                    detected_at=context.measured_at,
                    source="validated-fixture",
                    algorithm_key=f"{sector.lower()}.observation",
                    algorithm_version="1.0.0",
                    confidence=0.9,
                ),
            )
        ),
    )
    context = EvaluationContext("asset", sector, at)
    calculated = calculators.registrations(sector)[0].calculate(context)
    outcome = rules.registrations(sector)[0].evaluate(context, {metric: calculated})
    assert outcome is not None
    assert outcome.observations[0].observation_type == observation_type


def test_historical_comparison_keeps_previous_and_baseline_distinct():
    start = datetime(2026, 9, 1)
    comparison = historical_comparison(
        [
            HistoricalValue(10, start, is_baseline=True),
            HistoricalValue(15, start + timedelta(days=1)),
            HistoricalValue(25, start + timedelta(days=2)),
        ]
    )
    assert comparison.current == 25
    assert comparison.previous == 15
    assert comparison.baseline == 10
    assert comparison.change == 10
    assert comparison.change_percent == pytest.approx(66.6666667)
    assert comparison.baseline_change == 15
    assert comparison.baseline_change_percent == 150


def test_evaluation_persists_provenance_and_drives_normalized_customer_apis(
    client, db_session
):
    owner, organization_id, workspace_id, asset_payload, headers = _workspace_asset(
        client, db_session
    )
    asset = db_session.get(Asset, asset_payload["id"])
    assert asset is not None
    now = datetime(2026, 9, 10, 8)
    definition = KpiDefinitionSpec(
        sector="AGRICULTURE",
        key="area_needing_attention",
        name="Area needing attention",
        unit="ha",
        calculator="agriculture.attention_area",
        version="2.0.0",
        importance=KpiImportance.PRIMARY,
        display_format={"decimal_places": 1},
        status_policy={
            "mode": "lower_is_better",
            "good_max": 10,
            "watch_max": 20,
            "warning_max": 30,
            "minimum_confidence": 0.5,
        },
    )
    record_kpi_value(
        db_session,
        asset=asset,
        definition=definition,
        calculation=KpiCalculation(
            10,
            now - timedelta(days=30),
            "validated-baseline",
            0.95,
            {"kind": "baseline"},
        ),
        is_baseline=True,
    )
    record_kpi_value(
        db_session,
        asset=asset,
        definition=definition,
        calculation=KpiCalculation(
            15,
            now - timedelta(days=7),
            "drone-derived",
            0.88,
            {"dataset_sha256": "a" * 64},
        ),
    )

    calculators = CalculatorRegistry()
    calculators.register(
        definition,
        lambda context: KpiCalculation(
            value=float(context.measurements["attention_area_ha"]),
            measured_at=context.measured_at,
            source="multispectral-analysis",
            confidence=0.82,
            provenance={"input_band": "NIR", "validated_input": True},
        ),
    )
    rules = RuleRegistry()

    def attention_rule(context, values):
        result = values["area_needing_attention"]
        if float(result.value) <= 20:
            return RuleOutcome()
        return RuleOutcome(
            observations=(
                ObservationProposal(
                    key="attention-zone",
                    observation_type="CROP_STRESS_ZONE",
                    severity=ObservationSeverity.WARNING,
                    geometry={"type": "Point", "coordinates": [13.1, -8.9]},
                    value={"affected_hectares": result.value},
                    numeric_value=float(result.value),
                    unit="ha",
                    confidence=0.58,
                    source="multispectral-analysis",
                    algorithm_key="agriculture.attention_rule",
                    algorithm_version="1.1.0",
                    provenance={"kpi_key": "area_needing_attention"},
                    validation_status=ValidationStatus.NEEDS_REVIEW,
                    detected_at=context.measured_at,
                ),
            ),
            actions=(
                ActionRecommendation(
                    key="inspect-attention-zone",
                    priority="HIGH",
                    title="Inspect the attention zone",
                    description="Verify the mapped zone in the field before treatment decisions.",
                    source_observation_key="attention-zone",
                    due_date=context.measured_at + timedelta(days=2),
                    assigned_to_user_id=owner.id,
                    recommendation_refs=(
                        {"kind": "service", "code": "DETAILED_SURVEY"},
                    ),
                ),
            ),
        )

    rules.register(
        sector="AGRICULTURE",
        key="agriculture.attention_rule",
        version="1.1.0",
        evaluate=attention_rule,
    )
    evaluation = evaluate_asset(
        db_session,
        asset=asset,
        context=EvaluationContext(
            asset_id=asset.id,
            sector=asset.sector,
            measured_at=now,
            measurements={"attention_area_ha": 25},
        ),
        calculators=calculators,
        rules=rules,
    )
    actions = materialize_evaluation_actions(
        db_session, asset=asset, evaluation=evaluation, actor=owner
    )
    duplicate_actions = materialize_evaluation_actions(
        db_session, asset=asset, evaluation=evaluation, actor=owner
    )
    record_observation(
        db_session,
        asset=asset,
        proposal=ObservationProposal(
            key="informational-reading",
            observation_type="WEATHER_CONTEXT",
            severity=ObservationSeverity.INFO,
            confidence=0.96,
            source="weather-context",
            algorithm_key="agriculture.weather_context",
            algorithm_version="1.0.0",
            validation_status=ValidationStatus.VALIDATED,
            detected_at=now + timedelta(minutes=1),
        ),
    )
    db_session.commit()

    assert len(evaluation.kpi_values) == 1
    assert evaluation.kpi_values[0].status == "WARNING"
    assert evaluation.kpi_values[0].algorithm_version == "2.0.0"
    assert evaluation.observations[0].validation_status == "NEEDS_REVIEW"
    assert evaluation.observations[0].algorithm_version == "1.1.0"
    assert len(actions) == 1
    assert duplicate_actions[0].id == actions[0].id
    assert db_session.query(Action).filter(Action.asset_id == asset.id).count() == 1
    event_names = {
        row.event_type
        for row in db_session.query(EventOutbox)
        .filter(
            EventOutbox.aggregate_id.in_(
                [
                    evaluation.kpi_values[0].id,
                    evaluation.observations[0].id,
                    actions[0].id,
                ]
            )
        )
        .all()
    }
    assert {"kpi.updated", "observation.created", "action.requested"}.issubset(
        event_names
    )

    kpis = client.get(f"/assets/{asset.id}/kpis", headers=headers)
    assert kpis.status_code == 200, kpis.text
    item = kpis.json()["items"][0]
    assert item["definition"]["key"] == "area_needing_attention"
    assert item["definition"]["importance"] == "PRIMARY"
    assert item["current"] == 25
    assert item["previous"] == 15
    assert item["baseline"] == 10
    assert item["change"] == 10
    assert item["status"] == "WARNING"
    assert item["confidence"] == pytest.approx(0.82)
    assert item["provenance"]["calculator_version"] == "2.0.0"

    observations = client.get(
        f"/assets/{asset.id}/observations?severity=WARNING", headers=headers
    )
    assert observations.status_code == 200
    assert observations.json()["items"][0]["validation_status"] == "NEEDS_REVIEW"
    alerts = client.get(f"/assets/{asset.id}/alerts?limit=1", headers=headers)
    assert alerts.status_code == 200
    assert alerts.json()["warning_count"] == 1
    assert alerts.json()["unvalidated_count"] == 1
    summary = client.get(f"/assets/{asset.id}/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["status"] == "WARNING"
    assert summary.json()["open_action_count"] == 1
    assert summary.json()["unvalidated_observation_count"] == 1
    listed_actions = client.get("/actions", headers=headers)
    assert listed_actions.status_code == 200
    assert listed_actions.json()["items"][0]["source_rule_version"] == "1.1.0"

    no_outcome = client.patch(
        f"/actions/{actions[0].id}/status",
        headers=headers,
        json={"status": "COMPLETED", "expected_version": 1},
    )
    assert no_outcome.status_code == 409
    completed = client.patch(
        f"/actions/{actions[0].id}/status",
        headers=headers,
        json={
            "status": "COMPLETED",
            "expected_version": 1,
            "outcome": {"verified": True, "note": "Field inspection completed"},
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["outcome"]["verified"] is True
    stale = client.patch(
        f"/actions/{actions[0].id}/status",
        headers=headers,
        json={"status": "IN_PROGRESS", "expected_version": 1},
    )
    assert stale.status_code == 409

    viewer = _user(db_session, "intelligence-viewer")
    membership = client.post(
        f"/organizations/{organization_id}/members",
        headers=headers,
        json={"email": viewer.email, "user_id": viewer.id, "role": "viewer"},
    )
    assert membership.status_code == 201, membership.text
    viewer_headers = _headers(viewer, workspace_id)
    assert (
        client.get(f"/assets/{asset.id}/summary", headers=viewer_headers).status_code
        == 200
    )
    denied = client.patch(
        f"/actions/{actions[0].id}",
        headers=viewer_headers,
        json={"expected_version": 2, "assigned_to_user_id": viewer.id},
    )
    assert denied.status_code == 403

    outsider, _, outsider_workspace, _, outsider_headers = _workspace_asset(
        client, db_session, "intelligence-outsider"
    )
    assert outsider.id
    assert outsider_workspace != workspace_id
    assert (
        client.get(f"/assets/{asset.id}/kpis", headers=outsider_headers).status_code
        == 404
    )
    assert (
        client.get(f"/actions/{actions[0].id}", headers=outsider_headers).status_code
        == 404
    )
