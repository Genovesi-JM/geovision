from __future__ import annotations

from datetime import datetime
import hashlib
import json
import uuid

import pytest

from app.core.tokens import create_user_access_token
from app.integrations.storage.local import LocalObjectStorageProvider
from app.models import (
    Account,
    AccountMember,
    Action,
    Asset,
    AuditLog,
    Company,
    CompanyUser,
    Dataset,
    DatasetFile,
    EventOutbox,
    KpiDefinition,
    KpiValue,
    Observation,
    Report,
    Acquisition,
    User,
)
from app.modules.identity.domain import AuthorizationContext
from app.modules.organizations.domain import InternalRole, internal_permissions
from app.modules.reports.context_builder import ReportContextBuilder
from app.modules.reports.domain import ReportError
from app.modules.reports.qa import validate_narrative
from app.modules.reports.schemas import ReportGenerateRequest
from app.modules.reports.services import (
    approve_report,
    authorize_asset,
    download_report,
    generate_report,
    get_authorized_report,
    publish_report,
    submit_report,
)
from app.services.storage import StorageService


def _id() -> str:
    return str(uuid.uuid4())


def _fixture(db_session):
    now = datetime(2026, 9, 10, 8)
    organization = Company(
        id=_id(),
        name="Report organization",
        email=f"report-{_id()}@example.test",
        country="Angola",
        status="active",
    )
    workspace = Account(
        id=_id(),
        organization_id=organization.id,
        name="Report workspace",
        sector_focus="agro",
        entity_type="business",
        customer_type="business",
        dashboard_profile="farm",
    )
    actor = User(
        id=_id(),
        email=f"analyst-{_id()}@example.test",
        role="cliente",
        is_active=True,
    )
    asset = Asset(
        id=_id(),
        organization_id=organization.id,
        workspace_id=workspace.id,
        sector="AGRICULTURE",
        asset_type="FIELD",
        name="West field",
        status="active",
        geometry_geojson=json.dumps(
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [13.1, -8.9],
                        [13.2, -8.9],
                        [13.2, -8.8],
                        [13.1, -8.9],
                    ]
                ],
            }
        ),
        metadata_json="{}",
        created_by_user_id=actor.id,
        updated_by_user_id=actor.id,
        created_at=now,
        updated_at=now,
    )
    db_session.add_all((organization, workspace, actor, asset))
    db_session.flush()
    dataset = Dataset(
        id=_id(),
        company_id=organization.id,
        workspace_id=workspace.id,
        asset_id=asset.id,
        name="Validated analysis",
        dataset_type="NDVI",
        provider_code="fixture-provider",
        storage_provider="local",
        processing_level="DERIVED",
        quality_status="PASSED",
        status="ready",
        sector="AGRICULTURE",
        capture_date=now,
        provenance_json=json.dumps(
            {
                "processor": "fixture-processor",
                "processor_version": "1.0.0",
                "storage_key": "hidden",
            }
        ),
        metadata_json="{}",
        created_at=now,
        updated_at=now,
    )
    input_file = DatasetFile(
        id=_id(),
        dataset_id=dataset.id,
        filename="validated.tif",
        storage_key="private/source.tif",
        storage_uri="local://private/source.tif",
        storage_provider="local",
        object_area="derived",
        file_size=128,
        mime_type="image/tiff",
        sha256_hash="a" * 64,
        status="uploaded",
        confirmed_at=now,
        created_at=now,
    )
    definition = KpiDefinition(
        id=_id(),
        sector="AGRICULTURE",
        key="ndvi_mean",
        label="Mean NDVI",
        name="Mean NDVI",
        unit="index",
        calculator="agriculture.ndvi_mean",
        calculator_version="1.0.0",
        importance="PRIMARY",
        display_format_json="{}",
        status_policy_json="{}",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    eligible = KpiValue(
        id=_id(),
        kpi_definition_id=definition.id,
        account_id=workspace.id,
        organization_id=organization.id,
        workspace_id=workspace.id,
        asset_id=asset.id,
        dataset_id=dataset.id,
        value="0.6375",
        numeric_value=0.6375,
        status="GOOD",
        confidence=0.91,
        measured_at=now,
        source="drone:ndvi",
        algorithm_version="1.0.0",
        provenance_json=json.dumps({"dataset_id": dataset.id}),
        recorded_at=now,
        created_at=now,
    )
    rejected_kpi = KpiValue(
        id=_id(),
        kpi_definition_id=definition.id,
        account_id=workspace.id,
        organization_id=organization.id,
        workspace_id=workspace.id,
        asset_id=asset.id,
        value="9999",
        numeric_value=9999,
        status="UNKNOWN",
        confidence=0.2,
        measured_at=datetime(2026, 9, 10, 9),
        source="legacy",
        algorithm_version="legacy-1",
        provenance_json="{}",
        recorded_at=now,
        created_at=now,
    )
    validated = Observation(
        id=_id(),
        organization_id=organization.id,
        workspace_id=workspace.id,
        asset_id=asset.id,
        dataset_id=dataset.id,
        observation_type="CROP_STRESS",
        severity="WARNING",
        value_json=json.dumps({"area_ha": 3.25}),
        numeric_value=3.25,
        unit="ha",
        metadata_json="{}",
        confidence=0.88,
        source="drone:ndvi",
        algorithm_key="agriculture.crop_stress",
        algorithm_version="1.0.0",
        provenance_json="{}",
        validation_status="VALIDATED",
        validated_by_user_id=actor.id,
        validated_at=now,
        detected_at=now,
        created_at=now,
        updated_at=now,
    )
    unvalidated = Observation(
        id=_id(),
        organization_id=organization.id,
        workspace_id=workspace.id,
        asset_id=asset.id,
        dataset_id=dataset.id,
        observation_type="UNCONFIRMED_FINDING",
        severity="CRITICAL",
        value_json=json.dumps({"invented": 7777}),
        metadata_json="{}",
        confidence=0.99,
        source="fixture",
        algorithm_key="fixture.unconfirmed",
        algorithm_version="1.0.0",
        provenance_json="{}",
        validation_status="NEEDS_REVIEW",
        detected_at=now,
        created_at=now,
        updated_at=now,
    )
    action = Action(
        id=_id(),
        organization_id=organization.id,
        workspace_id=workspace.id,
        asset_id=asset.id,
        source_observation_id=validated.id,
        source_rule_key="agriculture.crop_stress",
        source_rule_version="1.0.0",
        priority="HIGH",
        title="Inspect the affected zone",
        description="Validate conditions before treatment.",
        status="OPEN",
        recommendation_refs_json="[]",
        outcome_json="{}",
        deduplication_key=f"report-fixture:{asset.id}",
        created_by_user_id=actor.id,
        created_at=now,
        updated_at=now,
    )
    db_session.add_all(
        (
            dataset,
            input_file,
            definition,
            eligible,
            rejected_kpi,
            validated,
            unvalidated,
            action,
        )
    )
    db_session.commit()
    return organization, workspace, actor, asset, eligible, validated, unvalidated


def _staff_context(user: User) -> AuthorizationContext:
    permissions = internal_permissions((InternalRole.ANALYST,))
    return AuthorizationContext(
        user_id=user.id,
        identity_subject=f"internal:{user.id}",
        internal_roles=frozenset({InternalRole.ANALYST.value}),
        permissions=frozenset({"profile:read", *permissions}),
    )


def _customer_context(user: User, organization: Company, workspace: Account):
    return AuthorizationContext(
        user_id=user.id,
        identity_subject=f"internal:{user.id}",
        active_workspace_id=workspace.id,
        active_organization_id=organization.id,
        workspace_role="viewer",
        organization_role="viewer",
        permissions=frozenset({"profile:read", "asset:read", "report:read"}),
    )


def _storage(tmp_path) -> StorageService:
    return StorageService(
        LocalObjectStorageProvider(
            root=tmp_path,
            public_base_url="http://testserver",
            signing_secret="test-report-storage-signing-secret",
        )
    )


def _published_report(
    db_session,
    *,
    organization: Company,
    workspace_id: str | None,
    actor: User,
    asset: Asset,
    title: str,
) -> Report:
    now = datetime(2026, 9, 10, 10)
    report = Report(
        id=_id(),
        organization_id=organization.id,
        workspace_id=workspace_id,
        asset_id=asset.id,
        report_type="ASSET_INTELLIGENCE",
        title=title,
        template_version="1.0.0",
        revision=1,
        status="PUBLISHED",
        qa_level="AUTO_APPROVED",
        context_schema_version="geovision.report-context.v1",
        context_json="{}",
        context_sha256="a" * 64,
        narrative_provider="deterministic",
        narrative_model_version="geovision-deterministic-v1.0.0",
        narrative_schema_version="geovision.report-narrative.v1",
        narrative_json="{}",
        provenance_json="{}",
        qa_result_json="{}",
        generation_key=f"route-test:{_id()}",
        generated_at=now,
        approved_at=now,
        published_at=now,
        created_by_user_id=actor.id,
        lifecycle_version=1,
        created_at=now,
        updated_at=now,
    )
    db_session.add(report)
    db_session.flush()
    return report


def test_report_routes_quarantine_legacy_null_scope_in_multi_workspace_org(
    client,
    db_session,
):
    organization, workspace_a, actor, legacy_asset, _, _, _ = _fixture(db_session)
    workspace_b = Account(
        id=_id(),
        organization_id=organization.id,
        name="Report workspace B",
        sector_focus="agro",
        entity_type="business",
        customer_type="business",
        dashboard_profile="farm",
    )
    workspace_b_asset = Asset(
        id=_id(),
        organization_id=organization.id,
        workspace_id=workspace_b.id,
        sector="AGRICULTURE",
        asset_type="FIELD",
        name="Workspace B field",
        status="active",
        metadata_json="{}",
        created_by_user_id=actor.id,
        updated_by_user_id=actor.id,
    )
    legacy_asset.workspace_id = None
    db_session.add_all((workspace_b, workspace_b_asset))
    db_session.flush()
    db_session.add_all(
        (
            CompanyUser(
                id=_id(),
                company_id=organization.id,
                user_id=actor.id,
                email=actor.email,
                role="viewer",
                is_active=True,
                status="active",
            ),
            AccountMember(
                account_id=workspace_b.id,
                user_id=actor.id,
                role="viewer",
                status="active",
            ),
        )
    )
    legacy_report = _published_report(
        db_session,
        organization=organization,
        workspace_id=None,
        actor=actor,
        asset=legacy_asset,
        title="Ambiguous legacy report",
    )
    workspace_b_report = _published_report(
        db_session,
        organization=organization,
        workspace_id=workspace_b.id,
        actor=actor,
        asset=workspace_b_asset,
        title="Workspace B report",
    )
    db_session.commit()

    token = create_user_access_token(
        user_id=actor.id,
        email=actor.email,
        role=actor.role,
        auth_generation=actor.auth_generation,
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": workspace_b.id,
    }

    listing = client.get("/reports", headers=headers)
    assert listing.status_code == 200, listing.text
    report_ids = {row["id"] for row in listing.json()["items"]}
    assert workspace_b_report.id in report_ids
    assert legacy_report.id not in report_ids

    detail = client.get(f"/reports/{legacy_report.id}", headers=headers)
    assert detail.status_code == 404, detail.text
    download = client.get(
        f"/reports/{legacy_report.id}/download",
        headers=headers,
    )
    assert download.status_code == 404, download.text

    explicit_detail = client.get(
        f"/reports/{workspace_b_report.id}",
        headers=headers,
    )
    assert explicit_detail.status_code == 200, explicit_detail.text
    assert explicit_detail.json()["id"] == workspace_b_report.id


def test_context_excludes_unvalidated_low_confidence_and_storage_locations(db_session):
    _, _, _, asset, eligible, validated, unvalidated = _fixture(db_session)
    built = ReportContextBuilder().build(db_session, asset=asset)

    assert [item["id"] for item in built.context["kpis"]] == [eligible.id]
    assert [item["id"] for item in built.context["observations"]] == [validated.id]
    assert unvalidated.id not in built.canonical_json
    assert "9999" not in built.canonical_json
    assert "private/source.tif" not in built.canonical_json
    assert "storage_key" not in built.canonical_json
    assert built.context["actions"][0]["source_observation_id"] == validated.id
    assert built.context["files"][0]["filename"] == "validated.tif"


def test_narrative_rejects_unknown_fields_numbers_and_evidence():
    base = {
        "schema_version": "geovision.report-narrative.v1",
        "executive_summary": "Validated evidence is available.",
        "sections": [{"heading": "Findings", "paragraphs": ["Review the evidence."]}],
        "evidence_ids": ["kpi:known"],
        "limitations": [],
    }
    with pytest.raises(ReportError, match="unsupported structured response"):
        validate_narrative(
            {**base, "unknown": True}, evidence_ids=frozenset({"kpi:known"})
        )
    with pytest.raises(ReportError, match="numeric literals"):
        validate_narrative(
            {**base, "executive_summary": "The value is 9000."},
            evidence_ids=frozenset({"kpi:known"}),
        )
    with pytest.raises(ReportError, match="outside the report context"):
        validate_narrative(base, evidence_ids=frozenset({"kpi:different"}))


class _UnavailableNarrative:
    provider_name = "azure_openai"
    model_name = "unavailable-deployment"
    model_version = "2026-09-10"

    def generate(self, context):
        del context
        raise RuntimeError("provider outage with secret-like diagnostic")


def test_generation_falls_back_stores_exact_pdf_and_is_idempotent(db_session, tmp_path):
    _, _, actor, asset, eligible, _, _ = _fixture(db_session)
    request = ReportGenerateRequest(
        report_type="AGRICULTURE_INTELLIGENCE",
        idempotency_key=f"report-{_id()}",
    )
    report, created = generate_report(
        db_session,
        actor=actor,
        asset=asset,
        data=request,
        narrative_provider=_UnavailableNarrative(),
        storage=_storage(tmp_path),
    )
    db_session.commit()
    assert created is True
    assert report.status == "DRAFT"
    assert report.qa_level == "HUMAN_REVIEW"
    assert report.narrative_provider == "deterministic"
    assert report.narrative_model_version == "geovision-deterministic-v1.0.0"
    provenance = json.loads(report.provenance_json)
    assert provenance["complete"] is True
    assert provenance["context_sha256"] == report.context_sha256
    assert provenance["template_version"] == report.template_version
    assert {
        (source["kind"], source["id"], source["version"])
        for source in provenance["sources"]
    } >= {
        ("dataset", eligible.dataset_id, "1.0.0"),
        ("kpi", eligible.id, "1.0.0"),
    }
    qa = json.loads(report.qa_result_json)
    assert qa["fallback_used"] is True
    assert qa["fallback_reason"] == "provider_unavailable"
    assert "secret-like" not in report.qa_result_json
    assert report.output_dataset_id and report.output_file_id

    content, filename = download_report(
        db_session,
        report=report,
        storage=_storage(tmp_path),
    )
    assert content.startswith(b"%PDF-")
    assert eligible.value.encode() in content
    assert filename.endswith(".pdf")
    assert b"Evidence provenance" in content
    assert b"geovision-deterministic-v1.0.0" in content
    file = db_session.get(DatasetFile, report.output_file_id)
    assert file.sha256_hash == hashlib.sha256(content).hexdigest()

    replay, replay_created = generate_report(
        db_session,
        actor=actor,
        asset=asset,
        data=request,
        narrative_provider=_UnavailableNarrative(),
        storage=_storage(tmp_path),
    )
    assert replay.id == report.id
    assert replay_created is False
    assert db_session.query(Report).filter(Report.asset_id == asset.id).count() == 1


def test_review_publication_permissions_audit_and_events(db_session, tmp_path):
    organization, workspace, actor, asset, _, _, _ = _fixture(db_session)
    report, _ = generate_report(
        db_session,
        actor=actor,
        asset=asset,
        data=ReportGenerateRequest(report_type="AGRICULTURE_INTELLIGENCE"),
        storage=_storage(tmp_path),
    )
    staff = _staff_context(actor)
    customer = _customer_context(actor, organization, workspace)

    with pytest.raises(ReportError):
        authorize_asset(
            db_session,
            context=customer,
            asset=asset,
            permission="report:generate",
        )
    with pytest.raises(ReportError):
        get_authorized_report(db_session, context=customer, report_id=report.id)

    submit_report(db_session, report=report, actor=actor, expected_version=1)
    approve_report(
        db_session,
        report=report,
        actor=actor,
        context=staff,
        expected_version=2,
    )
    publish_report(db_session, report=report, actor=actor, expected_version=3)
    db_session.commit()
    assert report.status == "PUBLISHED"
    assert report.lifecycle_version == 4
    assert (
        get_authorized_report(db_session, context=customer, report_id=report.id).id
        == report.id
    )

    actions = {
        row.action
        for row in db_session.query(AuditLog)
        .filter(AuditLog.resource_type == "report", AuditLog.resource_id == report.id)
        .all()
    }
    assert {
        "report.generated",
        "report.review_requested",
        "report.approved",
        "report.published",
    }.issubset(actions)
    events = {
        row.event_type
        for row in db_session.query(EventOutbox)
        .filter(
            EventOutbox.aggregate_type == "report",
            EventOutbox.aggregate_id == report.id,
        )
        .all()
    }
    assert {
        "report.generated",
        "report.review_requested",
        "report.approved",
        "report.published",
    }.issubset(events)


def test_mission_report_propagates_source_provider_and_versions_to_publication(
    db_session, tmp_path
):
    organization, workspace, actor, asset, kpi, observation, _ = _fixture(db_session)
    mission = Acquisition(
        id=_id(),
        acquisition_number=f"ACQ-{uuid.uuid4().hex[:12]}",
        organization_id=organization.id,
        workspace_id=workspace.id,
        asset_id=asset.id,
        acquisition_type="DRONE",
        title="Versioned inspection mission",
        state="COMPLETED",
        provider_code="flight-provider",
        provenance_json=json.dumps({"adapter_version": "flight-adapter-2.1.0"}),
        created_by_user_id=actor.id,
        updated_by_user_id=actor.id,
        created_at=datetime(2026, 9, 10, 7),
        updated_at=datetime(2026, 9, 10, 8),
    )
    dataset = db_session.get(Dataset, kpi.dataset_id)
    dataset.mission_id = mission.id
    kpi.mission_id = mission.id
    observation.mission_id = mission.id
    db_session.add(mission)
    db_session.commit()

    report, _ = generate_report(
        db_session,
        actor=actor,
        asset=asset,
        data=ReportGenerateRequest(
            report_type="AGRICULTURE_INTELLIGENCE",
            acquisition_id=mission.id,
        ),
        storage=_storage(tmp_path),
    )
    provenance = json.loads(report.provenance_json)
    mission_source = next(
        source for source in provenance["sources"] if source["kind"] == "mission"
    )
    assert mission_source == {
        "id": mission.id,
        "kind": "mission",
        "provider": "flight-provider",
        "version": "flight-adapter-2.1.0",
        "version_basis": "provider_or_adapter",
    }
    assert provenance["acquisition_id"] == mission.id
    assert provenance["complete"] is True

    staff = _staff_context(actor)
    submit_report(db_session, report=report, actor=actor)
    approve_report(db_session, report=report, actor=actor, context=staff)
    publish_report(db_session, report=report, actor=actor)
    db_session.commit()
    assert report.status == "PUBLISHED"


@pytest.mark.parametrize(
    ("provider_code", "legacy_source", "adapter_version"),
    [
        (
            "geovision_manual",
            "asset_inspection",
            "geovision-legacy-inspection-sync-v1.0.0",
        ),
        (
            "dji_mobile_sdk",
            "drone_mission",
            "geovision-legacy-drone-sync-v1.0.0",
        ),
    ],
)
def test_legacy_first_party_missions_remain_publishable_with_versioned_provenance(
    db_session,
    tmp_path,
    provider_code,
    legacy_source,
    adapter_version,
):
    organization, workspace, actor, asset, kpi, observation, _ = _fixture(db_session)
    mission = Acquisition(
        id=_id(),
        acquisition_number=f"ACQ-{uuid.uuid4().hex[:12]}",
        organization_id=organization.id,
        workspace_id=workspace.id,
        asset_id=asset.id,
        acquisition_type=(
            "MANUAL_INSPECTION" if legacy_source == "asset_inspection" else "DRONE"
        ),
        title="Versioned legacy source",
        state="COMPLETED",
        provider_code=provider_code,
        provenance_json=json.dumps(
            {"source": legacy_source, "adapter_version": adapter_version}
        ),
        legacy_source=legacy_source,
        legacy_source_id=_id(),
        created_by_user_id=actor.id,
        updated_by_user_id=actor.id,
        created_at=datetime(2026, 9, 10, 7),
        updated_at=datetime(2026, 9, 10, 8),
    )
    dataset = db_session.get(Dataset, kpi.dataset_id)
    dataset.mission_id = mission.id
    kpi.mission_id = mission.id
    observation.mission_id = mission.id
    db_session.add(mission)
    db_session.commit()

    report, _ = generate_report(
        db_session,
        actor=actor,
        asset=asset,
        data=ReportGenerateRequest(
            report_type="AGRICULTURE_INTELLIGENCE",
            acquisition_id=mission.id,
        ),
        storage=_storage(tmp_path),
    )
    mission_source = next(
        source
        for source in json.loads(report.provenance_json)["sources"]
        if source["kind"] == "mission"
    )
    assert mission_source["version"] == adapter_version
    assert mission_source["provider"] == provider_code

    staff = _staff_context(actor)
    submit_report(db_session, report=report, actor=actor)
    approve_report(db_session, report=report, actor=actor, context=staff)
    publish_report(db_session, report=report, actor=actor)
    assert report.status == "PUBLISHED"


def test_publication_rejects_tampered_or_incomplete_provenance(db_session, tmp_path):
    _, _, actor, asset, _, _, _ = _fixture(db_session)
    report, _ = generate_report(
        db_session,
        actor=actor,
        asset=asset,
        data=ReportGenerateRequest(report_type="AGRICULTURE_INTELLIGENCE"),
        storage=_storage(tmp_path),
    )
    submit_report(db_session, report=report, actor=actor)
    approve_report(
        db_session,
        report=report,
        actor=actor,
        context=_staff_context(actor),
    )
    report.provenance_json = "{}"

    with pytest.raises(ReportError, match="provenance is incomplete") as exc_info:
        publish_report(db_session, report=report, actor=actor)

    assert exc_info.value.code == "provenance_incomplete"
