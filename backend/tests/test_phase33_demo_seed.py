from __future__ import annotations

from types import SimpleNamespace
import json

import pytest

import app.phase33_demo as demo_seed
from app.core.passwords import hash_password
from app.models import (
    Account,
    AccountMember,
    Acquisition,
    Action,
    Asset,
    Company,
    CompanyUser,
    Dataset,
    KpiDefinition,
    KpiValue,
    Observation,
    Report,
    User,
)
from app.modules.analytics.domain import calculate_kpi_status
from scripts.seed_phase33_demo import main as seed_cli_main


EXPECTED_SECTORS = {
    "AGRICULTURE",
    "ENVIRONMENTAL",
    "INFRASTRUCTURE",
    "MINING",
    "PORTS_INDUSTRIAL",
}


def _marker(value: str | None) -> dict:
    body = json.loads(value or "{}")
    assert body["demo_seed"]["marker"] == demo_seed.PHASE33_DEMO_MARKER
    assert body["demo_seed"]["synthetic"] is True
    return body


def _counts(db_session, organization_id: str) -> dict[str, int]:
    return {
        "assets": db_session.query(Asset)
        .filter(Asset.organization_id == organization_id)
        .count(),
        "acquisitions": db_session.query(Acquisition)
        .filter(Acquisition.organization_id == organization_id)
        .count(),
        "datasets": db_session.query(Dataset)
        .filter(Dataset.company_id == organization_id)
        .count(),
        "kpis": db_session.query(KpiValue)
        .filter(KpiValue.organization_id == organization_id)
        .count(),
        "observations": db_session.query(Observation)
        .filter(Observation.organization_id == organization_id)
        .count(),
        "actions": db_session.query(Action)
        .filter(Action.organization_id == organization_id)
        .count(),
        "reports": db_session.query(Report)
        .filter(Report.organization_id == organization_id)
        .count(),
    }


def test_phase33_seed_builds_all_histories_and_is_idempotent(db_session):
    first = demo_seed.seed_phase33_demo(db_session)
    db_session.commit()

    assert first.access_mode == "database_only"
    assert first.attached_user_id is None

    organization = db_session.get(Company, first.organization_id)
    workspace = db_session.get(Account, first.workspace_id)
    owner = db_session.get(User, first.owner_user_id)
    member = db_session.get(User, first.member_user_id)
    assert organization.name.startswith("[SYNTHETIC DEMO]")
    assert organization.email.endswith("@example.invalid")
    assert workspace.organization_id == organization.id
    assert demo_seed.PHASE33_DEMO_MARKER in workspace.use_cases
    assert owner.password_hash is None and member.password_hash is None
    assert owner.email.endswith("@example.invalid")
    assert member.email.endswith("@example.invalid")
    assert (
        db_session.query(CompanyUser)
        .filter(CompanyUser.company_id == organization.id)
        .count()
        == 2
    )
    assert (
        db_session.query(AccountMember)
        .filter(AccountMember.account_id == workspace.id)
        .count()
        == 2
    )

    assets = (
        db_session.query(Asset)
        .filter(Asset.organization_id == organization.id)
        .order_by(Asset.sector)
        .all()
    )
    assert {row.sector for row in assets} == EXPECTED_SECTORS
    assert set(first.asset_ids) == {
        "agriculture",
        "environmental",
        "infrastructure",
        "mining",
        "ports",
    }

    for asset in assets:
        assert asset.name.startswith("[SYNTHETIC DEMO]")
        _marker(asset.metadata_json)
        acquisitions = (
            db_session.query(Acquisition)
            .filter(Acquisition.asset_id == asset.id)
            .order_by(Acquisition.captured_at)
            .all()
        )
        datasets = (
            db_session.query(Dataset)
            .filter(Dataset.asset_id == asset.id)
            .order_by(Dataset.capture_date, Dataset.id)
            .all()
        )
        kpis = (
            db_session.query(KpiValue)
            .filter(KpiValue.asset_id == asset.id)
            .order_by(KpiValue.measured_at)
            .all()
        )
        observations = (
            db_session.query(Observation)
            .filter(Observation.asset_id == asset.id)
            .order_by(Observation.detected_at)
            .all()
        )
        actions = (
            db_session.query(Action)
            .filter(Action.asset_id == asset.id)
            .order_by(Action.created_at)
            .all()
        )
        reports = (
            db_session.query(Report)
            .filter(Report.asset_id == asset.id)
            .order_by(Report.revision)
            .all()
        )

        assert len(acquisitions) == 2
        assert len(datasets) >= 2
        assert len(kpis) == len(observations) == len(actions) == len(reports) == 2
        assert reports[1].supersedes_report_id == reports[0].id
        assert [row.status for row in reports] == ["DRAFT", "PUBLISHED"]
        assert reports[1].approved_at is not None
        assert reports[1].published_at is not None
        assert reports[1].lifecycle_version == 4
        assert all(row.organization_id == organization.id for row in acquisitions)
        assert all(row.workspace_id == workspace.id for row in acquisitions)
        assert all(row.company_id == organization.id for row in datasets)
        assert all(row.workspace_id == workspace.id for row in datasets)
        assert all(row.organization_id == organization.id for row in kpis)
        assert all(row.account_id == workspace.id for row in kpis)
        assert all(row.workspace_id == workspace.id for row in kpis)
        assert all(row.organization_id == organization.id for row in observations)
        assert all(row.workspace_id == workspace.id for row in observations)
        assert all(row.organization_id == organization.id for row in actions)
        assert all(row.workspace_id == workspace.id for row in actions)
        assert all(row.organization_id == organization.id for row in reports)
        assert all(row.workspace_id == workspace.id for row in reports)
        assert {row.mission_id for row in datasets} == {row.id for row in acquisitions}
        assert {row.mission_id for row in kpis} == {row.id for row in acquisitions}
        assert {row.mission_id for row in observations} == {
            row.id for row in acquisitions
        }
        assert {row.source_observation_id for row in actions} == {
            row.id for row in observations
        }
        assert {row.acquisition_id for row in reports} == {
            row.id for row in acquisitions
        }

        for row in acquisitions:
            assert row.title.startswith("[SYNTHETIC DEMO]")
            _marker(row.provenance_json)
            assert row.provider_code == "synthetic_fixture"
        for row in datasets:
            assert row.name.startswith("[SYNTHETIC DEMO]")
            assert row.source == "geovision.phase33.synthetic"
            _marker(row.provenance_json)
            _marker(row.metadata_json)
        for row in kpis:
            assert row.source == "geovision.phase33.synthetic"
            _marker(row.provenance_json)
            policy = json.loads(row.definition.status_policy_json)
            assert policy
            assert row.status == calculate_kpi_status(
                float(row.numeric_value),
                policy,
                confidence=row.confidence,
            ).value
        for row in observations:
            assert row.source == "geovision.phase33.synthetic"
            _marker(row.provenance_json)
            _marker(row.metadata_json)
        for row in actions:
            assert row.title.startswith("[SYNTHETIC DEMO]")
            _marker(row.outcome_json)
        for row in reports:
            assert row.title.startswith("[SYNTHETIC DEMO]")
            assert row.output_dataset_id is None and row.output_file_id is None
            _marker(row.context_json)
            _marker(row.provenance_json)
            _marker(row.qa_result_json)
            _marker(row.narrative_json)
            assert demo_seed.PHASE33_DEMO_NOTICE in row.narrative_json

    before = _counts(db_session, organization.id)
    stable_ids = {
        model.__tablename__: tuple(
            row.id
            for row in db_session.query(model)
            .filter(
                (
                    model.organization_id == organization.id
                    if hasattr(model, "organization_id")
                    else model.company_id == organization.id
                )
            )
            .order_by(model.id)
            .all()
        )
        for model in (
            Asset,
            Acquisition,
            Dataset,
            KpiValue,
            Observation,
            Action,
            Report,
        )
    }
    second = demo_seed.seed_phase33_demo(db_session)
    db_session.commit()

    assert second.as_dict()["asset_ids"] == first.as_dict()["asset_ids"]
    assert second.created_total == 0
    assert _counts(db_session, organization.id) == before
    for model in (Asset, Acquisition, Dataset, KpiValue, Observation, Action, Report):
        scope = (
            model.organization_id == organization.id
            if hasattr(model, "organization_id")
            else model.company_id == organization.id
        )
        assert (
            tuple(
                row.id
                for row in db_session.query(model)
                .filter(scope)
                .order_by(model.id)
                .all()
            )
            == stable_ids[model.__tablename__]
        )


def test_phase33_seed_refuses_deployed_environments(db_session, monkeypatch):
    before = db_session.query(Company).count()
    monkeypatch.setattr(
        demo_seed,
        "settings",
        SimpleNamespace(is_deployed=True),
    )

    with pytest.raises(demo_seed.Phase33DemoSeedError, match="cannot run"):
        demo_seed.seed_phase33_demo(db_session)

    assert db_session.query(Company).count() == before


def test_phase33_cli_attaches_real_login_and_exposes_marked_five_sector_portal(
    client,
    db_session,
    capsys,
):
    email = "phase33-attached-local@example.com"
    password = "Phase33-local-demo-password-2026!"
    user = db_session.query(User).filter(User.email == email).one_or_none()
    if user is None:
        user = User(
            email=email,
            password_hash=hash_password(password),
            role="cliente",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    original_password_hash = user.password_hash

    assert (
        seed_cli_main(
            [
                "--confirm-synthetic-demo",
                "--attach-user-email",
                email,
            ]
        )
        == 0
    )
    cli_output = capsys.readouterr().out
    assert '"access_mode": "attached_local_user"' in cli_output
    assert demo_seed.PHASE33_DEMO_NOTICE in cli_output

    db_session.expire_all()
    user = db_session.query(User).filter(User.email == email).one()
    assert user.password_hash == original_password_hash
    rerun = demo_seed.seed_phase33_demo(db_session, attach_user_email=email)
    db_session.commit()
    assert rerun.created_total == 0
    assert rerun.attached_user_id == user.id
    assert rerun.access_mode == "attached_local_user"

    organization_membership = (
        db_session.query(CompanyUser)
        .filter(
            CompanyUser.company_id == rerun.organization_id,
            CompanyUser.user_id == user.id,
        )
        .one()
    )
    workspace_membership = db_session.get(
        AccountMember,
        (rerun.workspace_id, user.id),
    )
    assert organization_membership.role == "member"
    assert organization_membership.status == "active"
    assert workspace_membership is not None
    assert workspace_membership.role == "member"
    assert workspace_membership.status == "active"

    login = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    headers = {
        "Authorization": f"Bearer {login.json()['access_token']}",
        "X-Workspace-ID": rerun.workspace_id,
    }

    experience = client.get("/portal/experience", headers=headers)
    assert experience.status_code == 200, experience.text
    tree = experience.json()["asset_tree"]
    assert {item["sector"] for item in tree} == EXPECTED_SECTORS
    assert len(tree) == 5
    for item in tree:
        assert item["synthetic"] is True
        assert item["synthetic_marker"] == demo_seed.PHASE33_DEMO_MARKER
        assert item["synthetic_notice"] == demo_seed.PHASE33_DEMO_NOTICE
        assert item["source"] == "phase33_demo"

    summary = client.get("/portal/assets/summary", headers=headers)
    assert summary.status_code == 200, summary.text
    summary_body = summary.json()
    assert summary_body["totals"]["assets"] == 5
    assert summary_body["totals"]["published_reports"] == 5
    assert {item["sector"] for item in summary_body["items"]} == EXPECTED_SECTORS
    for item in summary_body["items"]:
        assert item["synthetic"] is True
        assert item["synthetic_marker"] == demo_seed.PHASE33_DEMO_MARKER
        assert item["synthetic_notice"] == demo_seed.PHASE33_DEMO_NOTICE
        cards = [*item["primary_kpis"], *item["secondary_kpis"]]
        assert len(cards) == 1
        assert cards[0]["synthetic"] is True
        assert cards[0]["synthetic_marker"] == demo_seed.PHASE33_DEMO_MARKER
        assert cards[0]["synthetic_notice"] == demo_seed.PHASE33_DEMO_NOTICE
        assert cards[0]["source"] == "geovision.phase33.synthetic"

    map_response = client.get("/portal/map-layers", headers=headers)
    assert map_response.status_code == 200, map_response.text
    layers = {item["id"]: item for item in map_response.json()["layers"]}
    assert len(layers["assets"]["feature_collection"]["features"]) == 5
    assert len(layers["observations"]["feature_collection"]["features"]) == 10
    for layer_name in ("assets", "observations"):
        for feature in layers[layer_name]["feature_collection"]["features"]:
            properties = feature["properties"]
            assert properties["synthetic"] is True
            assert properties["synthetic_marker"] == demo_seed.PHASE33_DEMO_MARKER
            assert properties["synthetic_notice"] == demo_seed.PHASE33_DEMO_NOTICE

    reports = client.get("/reports", headers=headers)
    assert reports.status_code == 200, reports.text
    assert reports.json()["total"] == 5
    for report in reports.json()["items"]:
        assert report["status"] == "PUBLISHED"
        assert report["title"].startswith("[SYNTHETIC DEMO]")
        assert report["published_at"] is not None
        assert report["provenance"]["demo_seed"] == {
            "marker": demo_seed.PHASE33_DEMO_MARKER,
            "notice": demo_seed.PHASE33_DEMO_NOTICE,
            "synthetic": True,
        }


@pytest.mark.parametrize(
    "model",
    (Asset, Acquisition, Dataset, KpiValue, Observation, Action, Report),
)
def test_phase33_seed_refuses_cross_workspace_drift(db_session, model):
    seeded = demo_seed.seed_phase33_demo(db_session)
    db_session.commit()
    other_workspace = Account(
        id=demo_seed.phase33_demo_id("test-workspace-drift", model.__tablename__),
        organization_id=seeded.organization_id,
        name=f"Drift target {model.__tablename__}",
        sector_focus="test",
        entity_type="company",
        customer_type="test",
        dashboard_profile="test",
        use_cases="[]",
        modules_enabled="[]",
        status="active",
    )
    db_session.add(other_workspace)
    db_session.flush()
    if model is Asset:
        row = db_session.get(Asset, seeded.asset_ids["agriculture"])
    else:
        row = (
            db_session.query(model)
            .filter(model.asset_id == seeded.asset_ids["agriculture"])
            .order_by(model.id)
            .first()
        )
    assert row is not None
    row.workspace_id = other_workspace.id
    db_session.flush()

    with pytest.raises(demo_seed.Phase33DemoSeedError, match="Refusing to overwrite"):
        demo_seed.seed_phase33_demo(db_session)
    db_session.rollback()


def test_phase33_seed_refuses_membership_and_kpi_definition_drift(db_session):
    seeded = demo_seed.seed_phase33_demo(db_session)
    db_session.commit()

    membership = db_session.get(
        AccountMember,
        (seeded.workspace_id, seeded.member_user_id),
    )
    assert membership is not None
    membership.status = "revoked"
    db_session.flush()
    with pytest.raises(
        demo_seed.Phase33DemoSeedError,
        match="membership relationship has drifted",
    ):
        demo_seed.seed_phase33_demo(db_session)
    db_session.rollback()

    definition = (
        db_session.query(KpiDefinition)
        .join(KpiValue, KpiValue.kpi_definition_id == KpiDefinition.id)
        .filter(KpiValue.asset_id == seeded.asset_ids["agriculture"])
        .one()
    )
    original_unit = definition.unit
    definition.unit = "incorrect-unit"
    db_session.flush()
    with pytest.raises(
        demo_seed.Phase33DemoSeedError,
        match="Existing KPI definition conflicts",
    ):
        demo_seed.seed_phase33_demo(db_session)
    db_session.rollback()
    assert db_session.get(KpiDefinition, definition.id).unit == original_unit
