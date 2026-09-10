from __future__ import annotations

from datetime import datetime
import hashlib
import json
import uuid

import pytest

from app.integrations.storage.local import LocalObjectStorageProvider
from app.models import (
    Account,
    Action,
    Asset,
    AuditLog,
    Company,
    Dataset,
    DatasetFile,
    EventOutbox,
    KpiDefinition,
    KpiValue,
    Observation,
    Report,
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
        storage_provider="local",
        processing_level="DERIVED",
        quality_status="PASSED",
        status="ready",
        sector="AGRICULTURE",
        capture_date=now,
        provenance_json=json.dumps({"algorithm": "fixture", "storage_key": "hidden"}),
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
        validate_narrative({**base, "unknown": True}, evidence_ids=frozenset({"kpi:known"}))
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

    def generate(self, context):
        del context
        raise RuntimeError("provider outage with secret-like diagnostic")


def test_generation_falls_back_stores_exact_pdf_and_is_idempotent(
    db_session, tmp_path
):
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
        authorize_asset(context=customer, asset=asset, permission="report:generate")
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
    assert get_authorized_report(
        db_session, context=customer, report_id=report.id
    ).id == report.id

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
        .filter(EventOutbox.aggregate_type == "report", EventOutbox.aggregate_id == report.id)
        .all()
    }
    assert {
        "report.generated",
        "report.review_requested",
        "report.approved",
        "report.published",
    }.issubset(events)
