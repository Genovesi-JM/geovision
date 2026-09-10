from __future__ import annotations

import uuid

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.event_names import EventNames
from app.core.time import utc_now
from app.core.tokens import create_user_access_token
from app.integrations.processing.fake import DeterministicProcessingProvider
from app.integrations.storage.local import LocalObjectStorageProvider
from app.models import (
    AccountEvent,
    AccountMember,
    Asset,
    CatalogItem,
    CompanyUser,
    Dataset,
    EventOutbox,
    MobileServiceRequest,
    Order,
    Payment,
    ProcessingJob,
    Site,
    User,
)
from app.modules.actions.services import create_action_from_recommendation
from app.modules.assets.services import archive_legacy_asset
from app.modules.analytics.domain import (
    ActionRecommendation,
    KpiCalculation,
    KpiDefinitionSpec,
    KpiImportance,
    KpiStatus,
    ObservationProposal,
    ObservationSeverity,
    ValidationStatus,
)
from app.modules.analytics.services import record_kpi_value, record_observation
from app.modules.identity.domain import AuthorizationContext
from app.modules.notifications.materializer import materialize_notification_event
from app.modules.operations import mobile_services
from app.modules.organizations.domain import InternalRole, internal_permissions
from app.modules.processing.services import run_processing_cycle
from app.modules.processing import services as processing_services
from app.modules.reports.schemas import ReportGenerateRequest
from app.modules.reports.services import (
    approve_report,
    generate_report,
    publish_report,
    submit_report,
)
from app.routers.datasets import _storage as dataset_storage_dependency
from app.services.event_outbox import event_from_row
from app.services.storage import StorageService


def _user(db_session, prefix: str, *, role: str = "cliente") -> User:
    row = User(
        email=f"{prefix}-{uuid.uuid4().hex}@example.com",
        role=role,
        is_active=True,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _headers(user: User, workspace_id: str | None = None) -> dict[str, str]:
    token = create_user_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        auth_generation=user.auth_generation,
    )
    result = {"Authorization": f"Bearer {token}"}
    if workspace_id:
        result["X-Workspace-ID"] = workspace_id
    return result


def _organization(client, owner: User, name: str) -> tuple[str, str]:
    response = client.post(
        "/organizations",
        headers=_headers(owner),
        json={
            "name": name,
            "country": "Angola",
            "timezone": "Africa/Luanda",
            "workspace": {
                "name": f"{name} workspace",
                "customer_type": "business",
                "sector_focus": "agro",
                "modules_enabled": ["projects", "alerts", "reports", "store"],
            },
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["id"], body["workspaces"][0]["id"]


def _staff_context(actor: User) -> AuthorizationContext:
    permissions = internal_permissions((InternalRole.SUPER_ADMIN,))
    return AuthorizationContext(
        user_id=actor.id,
        identity_subject=f"internal:{actor.id}",
        internal_roles=frozenset({InternalRole.SUPER_ADMIN.value}),
        permissions=frozenset({"profile:read", *permissions}),
    )


def test_service_request_has_one_durable_tenant_safe_journey(
    client,
    db_session,
    monkeypatch,
    tmp_path,
):
    suffix = uuid.uuid4().hex
    storage = StorageService(
        LocalObjectStorageProvider(
            root=tmp_path / "service-journey-objects",
            public_base_url="http://testserver",
            signing_secret="phase33-service-journey-signing-secret",
        )
    )
    monkeypatch.setitem(
        client.app.dependency_overrides,
        dataset_storage_dependency,
        lambda: storage,
    )
    owner = _user(db_session, "journey-owner")
    organization_id, workspace_id = _organization(
        client, owner, f"Service journey {suffix[:8]}"
    )
    owner_headers = _headers(owner, workspace_id)
    site_response = client.post(
        "/mobile/sites",
        headers=owner_headers,
        json={
            "name": "Journey Field",
            "sector": "agro",
            "country": "Angola",
            "province": "Huambo",
            "municipality": "Caála",
        },
    )
    assert site_response.status_code == 201, site_response.text
    site = site_response.json()

    request_body = {
        "site_id": site["id"],
        "site_name": "untrusted client label",
        "type": "drone_inspection",
        "urgency": "high",
        "description": "Inspect crop stress and deliver a verified report.",
        "attachments": ["customer-upload:brief-1"],
    }
    key = f"service-journey-{suffix}"
    created = client.post(
        "/mobile/service-requests",
        headers={**owner_headers, "Idempotency-Key": key},
        json=request_body,
    )
    assert created.status_code == 201, created.text
    service_request = created.json()
    replay = client.post(
        "/mobile/service-requests",
        headers={**owner_headers, "Idempotency-Key": key},
        json=request_body,
    )
    assert replay.status_code == 200, replay.text
    assert replay.headers["idempotency-replayed"] == "true"
    assert replay.json()["id"] == service_request["id"]
    conflict = client.post(
        "/mobile/service-requests",
        headers={**owner_headers, "Idempotency-Key": key},
        json={**request_body, "description": "A different request."},
    )
    assert conflict.status_code == 409

    # The idempotency fingerprint is derived from immutable request input. A
    # mutable authoritative site label must not turn an identical retry into a
    # false conflict after the first request committed.
    site_row = db_session.get(Site, site["id"])
    assert site_row is not None
    site_row.name = "Journey Field renamed after submission"
    db_session.commit()
    replay_after_rename = client.post(
        "/mobile/service-requests",
        headers={**owner_headers, "Idempotency-Key": key},
        json=request_body,
    )
    assert replay_after_rename.status_code == 200, replay_after_rename.text
    assert replay_after_rename.json()["id"] == service_request["id"]

    # Simulate both requests passing their first lookup before this committed
    # winner becomes visible. The losing insert must recover through the
    # tenant-qualified unique conflict instead of escaping as a 500.
    real_idempotency_lookup = mobile_services._idempotent_service_request
    hidden_lookup = {"remaining": 1}

    def lookup_after_competing_commit(*args, **kwargs):
        if hidden_lookup["remaining"]:
            hidden_lookup["remaining"] -= 1
            return None
        return real_idempotency_lookup(*args, **kwargs)

    monkeypatch.setattr(
        mobile_services,
        "_idempotent_service_request",
        lookup_after_competing_commit,
    )
    raced_replay = client.post(
        "/mobile/service-requests",
        headers={**owner_headers, "Idempotency-Key": key},
        json=request_body,
    )
    assert raced_replay.status_code == 200, raced_replay.text
    assert raced_replay.headers["idempotency-replayed"] == "true"
    assert raced_replay.json()["id"] == service_request["id"]

    hidden_lookup["remaining"] = 1
    raced_conflict = client.post(
        "/mobile/service-requests",
        headers={**owner_headers, "Idempotency-Key": key},
        json={**request_body, "description": "A raced but different request."},
    )
    assert raced_conflict.status_code == 409, raced_conflict.text
    db_session.expire_all()
    assert (
        db_session.query(MobileServiceRequest)
        .filter(
            MobileServiceRequest.organization_id == organization_id,
            MobileServiceRequest.workspace_id == workspace_id,
            MobileServiceRequest.user_id == owner.id,
            MobileServiceRequest.idempotency_key == key,
        )
        .count()
        == 1
    )
    created_events = (
        db_session.query(AccountEvent)
        .filter(
            AccountEvent.event_type == "service_request.created",
            AccountEvent.resource_id == service_request["id"],
        )
        .all()
    )
    assert len(created_events) == 1
    assert created_events[0].workspace_id == workspace_id

    persisted_request = db_session.get(MobileServiceRequest, service_request["id"])
    assert persisted_request is not None
    asset = db_session.get(Asset, persisted_request.asset_id)
    assert asset is not None
    assert (
        persisted_request.organization_id,
        persisted_request.workspace_id,
        asset.organization_id,
        asset.workspace_id,
    ) == (organization_id, workspace_id, organization_id, workspace_id)

    admin = db_session.query(User).filter(User.email == "teste@admin.com").one()
    admin_headers = _headers(admin)
    offer = CatalogItem(
        id=f"svc_{suffix[:24]}",
        code=f"SERVICE_JOURNEY_{suffix[:12].upper()}",
        slug=f"service-journey-{suffix[:16]}",
        item_type="SERVICE",
        name="Drone crop-stress inspection",
        sectors_json='["AGRICULTURE"]',
        asset_types_json='["SITE"]',
        customer_content_json="{}",
        deliverables_json='["REPORT"]',
        price_model="FIXED",
        currency="AOA",
        unit_amount=0,
        pricing_json='{"AOA":0}',
        availability_status="AVAILABLE",
        status="PUBLISHED",
        recommendation_triggers_json="[]",
        metadata_json="{}",
        published_at=utc_now(),
    )
    db_session.add(offer)
    db_session.commit()
    order_response = client.post(
        "/orders/internal",
        headers=admin_headers,
        json={
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "customer_id": owner.id,
            "currency": "AO",
            "items": [{"catalog_item_id": offer.id, "quantity": 1}],
        },
    )
    # Currency validation is deliberately exercised at the real boundary.
    assert order_response.status_code == 422
    order_response = client.post(
        "/orders/internal",
        headers=admin_headers,
        json={
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "customer_id": owner.id,
            "currency": "AOA",
            "items": [{"catalog_item_id": offer.id, "quantity": 1}],
        },
    )
    assert order_response.status_code == 201, order_response.text
    order = order_response.json()

    contractor_response = client.post(
        "/operations/contractors",
        headers=admin_headers,
        json={
            "code": f"PILOT_{suffix[:12].upper()}",
            "display_name": "Phase 33 field pilot",
            "resource_type": "PILOT",
            "country_code": "AO",
            "service_area": ["Huambo"],
            "equipment": [{"type": "drone", "model": "Mavic 3M"}],
        },
    )
    assert contractor_response.status_code == 201, contractor_response.text
    contractor = contractor_response.json()
    assignment_response = client.post(
        "/operations/assignments",
        headers=admin_headers,
        json={
            "contractor_id": contractor["id"],
            "order_id": order["id"],
            "title": "Capture Journey Field",
            "location": {"asset_id": asset.id},
            "requirements": {"capture": "RGB"},
            "upload_area": {"asset_id": asset.id},
            "required_documents": [],
        },
    )
    assert assignment_response.status_code == 201, assignment_response.text
    assignment = assignment_response.json()
    assert assignment["order_id"] == order["id"]

    mission_response = client.post(
        "/missions/internal",
        headers=admin_headers,
        json={
            "asset_id": asset.id,
            "order_id": order["id"],
            "acquisition_type": "DRONE",
            "title": "Journey Field capture",
            "provider_code": "geovision_field_ops",
            "provenance": {"adapter_version": "1.0.0"},
            "drone_details": {
                "contractor_id": contractor["id"],
                "mission_requirements": {"capture": "RGB"},
                "flight_metadata": {"assignment_id": assignment["id"]},
            },
        },
    )
    assert mission_response.status_code == 201, mission_response.text
    mission = mission_response.json()
    assert mission["order_id"] == order["id"]
    assert mission["drone_details"]["contractor_id"] == contractor["id"]

    dataset_response = client.post(
        "/datasets/",
        headers=owner_headers,
        json={
            "asset_id": asset.id,
            "mission_id": mission["id"],
            "name": "Journey RGB capture",
            "source_tool": "manual",
            "dataset_type": "RGB_IMAGES",
            "provider": "geovision_field_ops",
            "source": "drone_capture",
            "source_reference": assignment["id"],
            "sector": "AGRICULTURE",
            "processing_level": "RAW",
            "quality_status": "PASSED",
            "provenance": {
                "provider": "geovision_field_ops",
                "adapter_version": "1.0.0",
            },
        },
    )
    assert dataset_response.status_code == 201, dataset_response.text
    source_dataset = dataset_response.json()
    uploaded = client.post(
        f"/datasets/{source_dataset['id']}/upload",
        headers=owner_headers,
        files={"file": ("capture.jpg", b"\xff\xd8\xffGEOVISION", "image/jpeg")},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["status"] == "uploaded"
    second_upload = client.post(
        f"/datasets/{source_dataset['id']}/upload",
        headers=owner_headers,
        files={
            "file": (
                "capture-2.jpg",
                b"\xff\xd8\xffGEOVISION-SECOND",
                "image/jpeg",
            )
        },
    )
    assert second_upload.status_code == 200, second_upload.text
    finalized = client.post(
        f"/datasets/{source_dataset['id']}/finalize",
        headers=owner_headers,
    )
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["status"] == "ready"

    processing_response = client.post(
        "/processing/jobs",
        headers=admin_headers,
        json={
            "source_dataset_ids": [source_dataset["id"]],
            "requested_outputs": ["ORTHOMOSAIC"],
            "provider": "fake",
            "estimated_cost_amount": 0,
            "idempotency_key": f"processing-{suffix}",
        },
    )
    assert processing_response.status_code == 201, processing_response.text
    processing_job = db_session.get(ProcessingJob, processing_response.json()["id"])
    assert processing_job is not None

    # This integration fixture intentionally shares one database across tests.
    # Pin the journey worker to its exact job so an unrelated eligible job left
    # by an earlier suite cannot consume the one-item cycle.
    def claim_journey_job(db, *, worker_id: str, limit: int, config: Settings):
        del limit, config
        job = db.get(ProcessingJob, processing_job.id)
        assert job is not None
        job.claimed_by = worker_id
        job.claimed_at = utc_now()
        db.commit()
        return [job.id]

    monkeypatch.setattr(
        processing_services,
        "claim_processing_jobs",
        claim_journey_job,
    )
    config = Settings(
        _env_file=None,
        processing_provider="fake",
        processing_worker_poll_seconds=0.01,
        processing_retry_initial_seconds=0,
        processing_retry_max_seconds=0,
    )

    def resolver(_code: str) -> DeterministicProcessingProvider:
        return DeterministicProcessingProvider()

    submitted = run_processing_cycle(
        db_session,
        worker_id=f"journey-{suffix[:8]}",
        provider_resolver=resolver,
        storage=storage,
        config=config,
        limit=1,
    )
    assert submitted["submitted"] == 1
    db_session.refresh(processing_job)
    processing_job.next_poll_at = None
    db_session.commit()
    completed = run_processing_cycle(
        db_session,
        worker_id=f"journey-{suffix[:8]}",
        provider_resolver=resolver,
        storage=storage,
        config=config,
        limit=1,
    )
    assert completed["completed"] == 1
    db_session.refresh(processing_job)
    derived_id = processing_job.output_links[0].dataset_id
    derived = db_session.get(Dataset, derived_id)
    assert derived is not None
    assert (
        processing_job.organization_id,
        processing_job.workspace_id,
        processing_job.asset_id,
        processing_job.acquisition_id,
    ) == (organization_id, workspace_id, asset.id, mission["id"])

    measured_at = utc_now()
    kpi = record_kpi_value(
        db_session,
        asset=asset,
        definition=KpiDefinitionSpec(
            sector="AGRICULTURE",
            key=f"journey_health_{suffix[:8]}",
            name="Journey crop health",
            calculator="phase33.crop_health",
            version="1.0.0",
            unit="index",
            importance=KpiImportance.PRIMARY,
        ),
        calculation=KpiCalculation(
            value=0.42,
            measured_at=measured_at,
            source="phase33.processing",
            confidence=0.94,
            provenance={"processing_job_id": processing_job.id},
            status=KpiStatus.WARNING,
        ),
        workspace_id=workspace_id,
        mission_id=mission["id"],
        dataset_id=derived.id,
    )
    observation = record_observation(
        db_session,
        asset=asset,
        workspace_id=workspace_id,
        proposal=ObservationProposal(
            key=f"stress-{suffix[:8]}",
            observation_type="CROP_STRESS",
            severity=ObservationSeverity.WARNING,
            detected_at=measured_at,
            source="phase33.processing",
            algorithm_key="phase33.crop_stress",
            algorithm_version="1.0.0",
            confidence=0.92,
            value={"affected_percent": 12.5},
            numeric_value=12.5,
            unit="percent",
            provenance={"processing_job_id": processing_job.id},
            validation_status=ValidationStatus.VALIDATED,
            mission_id=mission["id"],
            dataset_id=derived.id,
        ),
    )
    action, action_created = create_action_from_recommendation(
        db_session,
        asset=asset,
        rule_key="phase33.crop_stress",
        rule_version="1.0.0",
        recommendation=ActionRecommendation(
            key=f"inspect-{suffix[:8]}",
            priority="HIGH",
            title="Inspect the crop-stress zone",
            description="Validate the detected stress before treatment.",
            source_observation_key=observation.id,
            recommendation_refs=({"kpi_value_id": kpi.id},),
        ),
        source_observation_id=observation.id,
        actor=admin,
    )
    assert action_created is True
    db_session.commit()
    assert (kpi.dataset_id, observation.dataset_id, action.source_observation_id) == (
        derived.id,
        derived.id,
        observation.id,
    )

    report, report_created = generate_report(
        db_session,
        actor=admin,
        asset=asset,
        data=ReportGenerateRequest(
            report_type="AGRICULTURE_INTELLIGENCE",
            title="Journey Field verified result",
            acquisition_id=mission["id"],
            idempotency_key=f"report-{suffix}",
        ),
        storage=storage,
    )
    assert report_created is True
    assert report.status == "DRAFT"
    submit_report(db_session, report=report, actor=admin, expected_version=1)
    approve_report(
        db_session,
        report=report,
        actor=admin,
        context=_staff_context(admin),
        expected_version=2,
    )
    publish_report(db_session, report=report, actor=admin, expected_version=3)
    db_session.commit()
    assert report.status == "PUBLISHED"
    assert report.acquisition_id == mission["id"]
    assert report.output_dataset_id is not None

    published_event = (
        db_session.query(EventOutbox)
        .filter(
            EventOutbox.event_type == EventNames.REPORT_PUBLISHED,
            EventOutbox.aggregate_id == report.id,
        )
        .one()
    )
    materialized_before_invite = materialize_notification_event(
        db_session, event_from_row(published_event)
    )
    published_event.status = "published"
    published_event.published_at = utc_now()
    db_session.commit()
    assert materialized_before_invite.created >= 1

    null_progress = client.patch(
        f"/operations/service-requests/{service_request['id']}",
        headers=admin_headers,
        json={
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "progress_percent": None,
            "expected_version": service_request["lifecycle_version"],
        },
    )
    assert null_progress.status_code == 422

    # Operations may prepare a published report link before customer release,
    # but it must remain invisible and unshareable until the lifecycle reaches
    # an explicit result state.
    prepared = client.patch(
        f"/operations/service-requests/{service_request['id']}",
        headers=admin_headers,
        json={
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "asset_id": asset.id,
            "report_id": report.id,
            "status": "scheduled",
            "progress_percent": 75,
            "expected_version": service_request["lifecycle_version"],
        },
    )
    assert prepared.status_code == 200, prepared.text
    assert prepared.json()["lifecycle_version"] == 2
    hidden_result = client.get(
        f"/mobile/service-requests/{service_request['id']}",
        headers=owner_headers,
    )
    assert hidden_result.status_code == 200, hidden_result.text
    assert hidden_result.json()["result"] is None
    premature_invitation = client.post(
        "/invitations",
        headers=owner_headers,
        json={
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "target_email": f"premature-{suffix}@example.com",
            "intended_role": "viewer",
            "target_type": "service_result",
            "target_id": service_request["id"],
        },
    )
    assert premature_invitation.status_code == 404

    missing_order_chain = client.patch(
        f"/operations/service-requests/{service_request['id']}",
        headers=admin_headers,
        json={
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "status": "results_ready",
            "expected_version": prepared.json()["lifecycle_version"],
        },
    )
    assert missing_order_chain.status_code == 409, missing_order_chain.text
    assert missing_order_chain.json()["detail"]["code"] == (
        "service_request_link_mismatch"
    )

    unrelated_order = Order(
        user_id=owner.id,
        company_id=organization_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        order_type="SERVICE",
        fulfilment_status="DRAFT",
        payment_status="PENDING",
        status="pending",
        currency="AOA",
    )
    db_session.add(unrelated_order)
    db_session.commit()
    mismatched_chain = client.patch(
        f"/operations/service-requests/{service_request['id']}",
        headers=admin_headers,
        json={
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "order_id": unrelated_order.id,
            "status": "results_ready",
            "expected_version": prepared.json()["lifecycle_version"],
        },
    )
    assert mismatched_chain.status_code == 409, mismatched_chain.text
    assert mismatched_chain.json()["detail"]["code"] == (
        "service_request_link_mismatch"
    )

    linked = client.patch(
        f"/operations/service-requests/{service_request['id']}",
        headers=admin_headers,
        json={
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "asset_id": asset.id,
            "order_id": order["id"],
            "report_id": report.id,
            "status": "results_ready",
            "progress_percent": 100,
            "assigned_team": "Phase 33 Operations",
            "expected_version": prepared.json()["lifecycle_version"],
        },
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["lifecycle_version"] == 3
    stale = client.patch(
        f"/operations/service-requests/{service_request['id']}",
        headers=admin_headers,
        json={
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "status": "completed",
            "expected_version": prepared.json()["lifecycle_version"],
        },
    )
    assert stale.status_code == 409

    verified_result = client.get(
        f"/mobile/service-requests/{service_request['id']}",
        headers=owner_headers,
    )
    assert verified_result.status_code == 200, verified_result.text
    assert verified_result.json()["result"]["report_id"] == report.id

    # Result links are capabilities, so every mutable target is revalidated at
    # read time rather than trusting a link that was valid only when attached.
    asset.workspace_id = None
    db_session.commit()
    stale_asset_result = client.get(
        f"/mobile/service-requests/{service_request['id']}",
        headers=owner_headers,
    )
    assert stale_asset_result.status_code == 200, stale_asset_result.text
    assert stale_asset_result.json()["result"] is None
    asset.workspace_id = workspace_id
    linked_order = db_session.get(Order, order["id"])
    assert linked_order is not None
    linked_order.workspace_id = None
    db_session.commit()
    stale_order_result = client.get(
        f"/mobile/service-requests/{service_request['id']}",
        headers=owner_headers,
    )
    assert stale_order_result.status_code == 200, stale_order_result.text
    assert stale_order_result.json()["result"] is None
    linked_order.workspace_id = workspace_id
    db_session.commit()

    recipient = _user(db_session, "journey-recipient")
    invitation = client.post(
        "/invitations",
        headers=owner_headers,
        json={
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "target_email": recipient.email,
            "intended_role": "finance",
            "target_type": "service_result",
            "target_id": service_request["id"],
        },
    )
    assert invitation.status_code == 201, invitation.text
    assert invitation.json()["destination"]["path"] == (
        f"/work/{service_request['id']}"
    )
    accepted = client.post(
        "/invitations/accept",
        headers=_headers(recipient),
        json={"token": invitation.json()["token"]},
    )
    assert accepted.status_code == 200, accepted.text
    recipient_headers = _headers(recipient, workspace_id)
    inbox = client.get("/notifications", headers=recipient_headers)
    assert inbox.status_code == 200, inbox.text
    report_notification = next(
        item for item in inbox.json()["items"] if item["target_type"] == "REPORT"
    )
    deep_link = client.get(
        f"/notifications/{report_notification['id']}/target",
        headers=recipient_headers,
    )
    assert deep_link.status_code == 200, deep_link.text
    assert deep_link.json()["app_path"] == f"/reports/{report.id}"

    service_history = client.get("/mobile/service-requests", headers=recipient_headers)
    assert service_history.status_code == 200, service_history.text
    history_item = next(
        item for item in service_history.json() if item["id"] == service_request["id"]
    )
    assert history_item["order_id"] == order["id"]
    assert history_item["result"]["report_id"] == report.id
    order_history = client.get("/orders", headers=recipient_headers)
    assert order_history.status_code == 200, order_history.text
    assert order["id"] in {item["id"] for item in order_history.json()}

    outsider = _user(db_session, "journey-outsider")
    other_organization_id, other_workspace_id = _organization(
        client, outsider, f"Other journey {suffix[:8]}"
    )
    other_headers = _headers(outsider, other_workspace_id)
    other_site_response = client.post(
        "/mobile/sites",
        headers=other_headers,
        json={
            "name": "Other Field",
            "sector": "agro",
            "country": "Angola",
            "province": "Huambo",
            "municipality": "Caála",
        },
    )
    assert other_site_response.status_code == 201, other_site_response.text
    other_site = other_site_response.json()
    same_key_other_scope = client.post(
        "/mobile/service-requests",
        headers={**other_headers, "Idempotency-Key": key},
        json={**request_body, "site_id": other_site["id"]},
    )
    assert same_key_other_scope.status_code == 201, same_key_other_scope.text
    assert same_key_other_scope.json()["id"] != service_request["id"]
    assert (
        client.get(
            f"/mobile/service-requests/{service_request['id']}",
            headers=other_headers,
        ).status_code
        == 404
    )
    assert (
        client.get(f"/datasets/{derived.id}", headers=other_headers).status_code == 404
    )
    cross_scope_link = client.patch(
        f"/operations/service-requests/{service_request['id']}",
        headers=admin_headers,
        json={
            "organization_id": other_organization_id,
            "workspace_id": other_workspace_id,
            "asset_id": same_key_other_scope.json()["asset_id"],
            "status": "processing",
            "expected_version": 2,
        },
    )
    assert cross_scope_link.status_code == 404


def test_phase33_one_identity_selects_only_its_authorized_workspaces(
    client,
    db_session,
):
    owner = _user(db_session, "multi-workspace-owner")
    organization_id, first_workspace_id = _organization(
        client, owner, f"Multi workspace {uuid.uuid4().hex[:8]}"
    )
    second = client.post(
        f"/organizations/{organization_id}/workspaces",
        headers=_headers(owner, first_workspace_id),
        json={
            "name": "Authorized second workspace",
            "customer_type": "business",
            "sector_focus": "infrastructure",
            "modules_enabled": ["projects", "alerts"],
        },
    )
    assert second.status_code == 201, second.text
    second_workspace_id = second.json()["id"]

    other_owner = _user(db_session, "multi-workspace-other-owner")
    _, forbidden_workspace_id = _organization(
        client, other_owner, f"Forbidden workspace {uuid.uuid4().hex[:8]}"
    )
    first_selected = client.get(
        "/mobile/experience", headers=_headers(owner, first_workspace_id)
    )
    second_selected = client.get(
        "/mobile/experience", headers=_headers(owner, second_workspace_id)
    )
    forbidden = client.get(
        "/mobile/experience", headers=_headers(owner, forbidden_workspace_id)
    )
    assert first_selected.status_code == 200, first_selected.text
    assert second_selected.status_code == 200, second_selected.text
    assert first_selected.json()["active_workspace_id"] == first_workspace_id
    assert second_selected.json()["active_workspace_id"] == second_workspace_id
    assert {row["id"] for row in first_selected.json()["workspaces"]} == {
        first_workspace_id,
        second_workspace_id,
    }
    assert forbidden.status_code == 403

    same_org_other_workspace_order = Order(
        user_id=owner.id,
        company_id=organization_id,
        organization_id=organization_id,
        workspace_id=second_workspace_id,
        order_type="SERVICE",
        fulfilment_status="DRAFT",
        payment_status="PENDING",
        status="pending",
        currency="AOA",
    )
    db_session.add(same_org_other_workspace_order)
    db_session.commit()
    recipient = _user(db_session, "cross-workspace-order-recipient")
    wrong_workspace_invitation = client.post(
        "/invitations",
        headers=_headers(owner, first_workspace_id),
        json={
            "organization_id": organization_id,
            "workspace_id": first_workspace_id,
            "target_email": recipient.email,
            "intended_role": "viewer",
            "target_type": "order",
            "target_id": same_org_other_workspace_order.id,
        },
    )
    assert wrong_workspace_invitation.status_code == 404
    matching_workspace_invitation = client.post(
        "/invitations",
        headers=_headers(owner, second_workspace_id),
        json={
            "organization_id": organization_id,
            "workspace_id": second_workspace_id,
            "target_email": recipient.email,
            "intended_role": "viewer",
            "target_type": "order",
            "target_id": same_org_other_workspace_order.id,
        },
    )
    assert matching_workspace_invitation.status_code == 201, (
        matching_workspace_invitation.text
    )


def test_phase33_account_activity_and_overview_are_workspace_scoped(
    client,
    db_session,
):
    owner = _user(db_session, "account-scope-owner")
    organization_id, workspace_a = _organization(
        client, owner, f"Account scope {uuid.uuid4().hex[:8]}"
    )
    second = client.post(
        f"/organizations/{organization_id}/workspaces",
        headers=_headers(owner, workspace_a),
        json={
            "name": "Private second workspace",
            "customer_type": "business",
            "sector_focus": "infrastructure",
            "modules_enabled": ["projects", "alerts"],
        },
    )
    assert second.status_code == 201, second.text
    workspace_b = second.json()["id"]

    limited = _user(db_session, "account-scope-limited")
    db_session.add_all(
        [
            CompanyUser(
                company_id=organization_id,
                user_id=limited.id,
                email=limited.email,
                role="member",
                is_active=True,
                status="active",
                joined_at=utc_now(),
            ),
            AccountMember(
                account_id=workspace_a,
                user_id=limited.id,
                role="member",
                status="active",
                joined_at=utc_now(),
            ),
        ]
    )
    db_session.commit()

    def create_site_and_request(workspace_id: str, label: str) -> tuple[dict, dict]:
        headers = _headers(owner, workspace_id)
        site_response = client.post(
            "/mobile/sites",
            headers=headers,
            json={
                "name": f"{label} confidential site",
                "sector": "agro",
                "country": "Angola",
                "province": "Huambo",
                "municipality": "Caála",
            },
        )
        assert site_response.status_code == 201, site_response.text
        site = site_response.json()
        request_response = client.post(
            "/mobile/service-requests",
            headers={
                **headers,
                "Idempotency-Key": f"account-scope-{label.lower()}-request",
            },
            json={
                "site_id": site["id"],
                "site_name": "ignored",
                "type": "inspection",
                "urgency": "normal",
                "description": f"{label} confidential request",
                "attachments": [],
            },
        )
        assert request_response.status_code == 201, request_response.text
        return site, request_response.json()

    _, request_a = create_site_and_request(workspace_a, "Alpha")
    _, request_b = create_site_and_request(workspace_b, "Bravo")
    order_a = Order(
        user_id=owner.id,
        company_id=organization_id,
        organization_id=organization_id,
        workspace_id=workspace_a,
        order_type="SERVICE",
        fulfilment_status="DRAFT",
        payment_status="PENDING",
        status="pending",
        currency="AOA",
    )
    order_b = Order(
        user_id=owner.id,
        company_id=organization_id,
        organization_id=organization_id,
        workspace_id=workspace_b,
        order_type="SERVICE",
        fulfilment_status="DRAFT",
        payment_status="PENDING",
        status="pending",
        currency="AOA",
    )
    db_session.add_all([order_a, order_b])
    db_session.flush()
    db_session.add_all(
        [
            Payment(
                company_id=organization_id,
                organization_id=organization_id,
                order_id=order_a.id,
                amount=111,
                currency="AOA",
                provider="mock",
                status="pending",
            ),
            Payment(
                company_id=organization_id,
                organization_id=organization_id,
                order_id=order_b.id,
                amount=999,
                currency="AOA",
                provider="mock",
                status="pending",
            ),
            AccountEvent(
                company_id=organization_id,
                workspace_id=workspace_a,
                event_type="service_request.updated",
                resource_type="service_request",
                resource_id=request_a["id"],
                title="Alpha sanitized update",
                payload_json='{"actor_user_id":"internal-user-secret","status":"scheduled"}',
            ),
            AccountEvent(
                company_id=organization_id,
                workspace_id=None,
                event_type="legacy.event",
                resource_type="legacy",
                resource_id=None,
                title="Legacy unscoped event",
                payload_json="{}",
            ),
        ]
    )
    db_session.commit()

    limited_headers = _headers(limited, workspace_a)
    events_a = client.get("/mobile/account/events", headers=limited_headers)
    assert events_a.status_code == 200, events_a.text
    serialized_events_a = events_a.json()
    titles_a = {item["title"] for item in serialized_events_a}
    assert any("Alpha confidential site" in title for title in titles_a)
    assert any("Alpha" in title for title in titles_a)
    assert not any("Bravo" in title for title in titles_a)
    assert "Legacy unscoped event" not in titles_a
    assert all("actor_user_id" not in item["data"] for item in serialized_events_a)
    assert {item["workspace_id"] for item in serialized_events_a} == {workspace_a}

    events_b = client.get(
        "/mobile/account/events",
        headers=_headers(owner, workspace_b),
    )
    assert events_b.status_code == 200, events_b.text
    titles_b = {item["title"] for item in events_b.json()}
    assert any("Bravo confidential site" in title for title in titles_b)
    assert not any("Alpha" in title for title in titles_b)
    assert "Legacy unscoped event" not in titles_b

    overview = client.get("/mobile/account/overview", headers=limited_headers)
    assert overview.status_code == 200, overview.text
    body = overview.json()
    assert body["financial"]["outstanding_cents"] == 111
    assert body["activity"] == {
        "sites": 1,
        "orders": 1,
        "active_orders": 1,
        "service_requests": 1,
        "active_requests": 1,
    }
    assert [row["id"] for row in body["recent_orders"]] == [order_a.id]
    assert (
        client.get(
            "/mobile/account/overview",
            headers=_headers(limited, workspace_b),
        ).status_code
        == 403
    )
    assert request_a["id"] != request_b["id"]


def test_phase33_service_request_lifecycle_is_forward_atomic_and_monotonic(
    client,
    db_session,
):
    owner = _user(db_session, "service-lifecycle-owner")
    organization_id, workspace_id = _organization(
        client, owner, f"Service lifecycle {uuid.uuid4().hex[:8]}"
    )
    site = client.post(
        "/mobile/sites",
        headers=_headers(owner, workspace_id),
        json={
            "name": "Lifecycle Field",
            "sector": "agro",
            "country": "Angola",
            "province": "Huambo",
            "municipality": "Caála",
        },
    ).json()
    created = client.post(
        "/mobile/service-requests",
        headers=_headers(owner, workspace_id),
        json={
            "site_id": site["id"],
            "site_name": "ignored",
            "type": "inspection",
            "urgency": "normal",
            "description": "Exercise the durable lifecycle.",
            "attachments": [],
        },
    )
    assert created.status_code == 201, created.text
    request = created.json()
    admin = db_session.query(User).filter(User.email == "teste@admin.com").one()
    endpoint = f"/operations/service-requests/{request['id']}"
    scope = {
        "organization_id": organization_id,
        "workspace_id": workspace_id,
    }

    scheduled = client.patch(
        endpoint,
        headers=_headers(admin),
        json={
            **scope,
            "status": "scheduled",
            "progress_percent": 25,
            "expected_version": 1,
        },
    )
    assert scheduled.status_code == 200, scheduled.text
    assert (
        scheduled.json()["status"],
        scheduled.json()["progress_percent"],
        scheduled.json()["lifecycle_version"],
    ) == ("scheduled", 25, 2)

    decreased = client.patch(
        endpoint,
        headers=_headers(admin),
        json={
            **scope,
            "status": "scheduled",
            "progress_percent": 20,
            "expected_version": 2,
        },
    )
    assert decreased.status_code == 409
    assert decreased.json()["detail"]["code"] == "invalid_service_request_progress"
    regressed = client.patch(
        endpoint,
        headers=_headers(admin),
        json={**scope, "status": "submitted", "expected_version": 2},
    )
    assert regressed.status_code == 409
    assert regressed.json()["detail"]["code"] == ("invalid_service_request_transition")

    in_field = client.patch(
        endpoint,
        headers=_headers(admin),
        json={
            **scope,
            "status": "in_field",
            "progress_percent": 50,
            "expected_version": 2,
        },
    )
    assert in_field.status_code == 200, in_field.text
    assert in_field.json()["lifecycle_version"] == 3
    stale = client.patch(
        endpoint,
        headers=_headers(admin),
        json={
            **scope,
            "status": "processing",
            "progress_percent": 75,
            "expected_version": 2,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"

    cancelled = client.patch(
        endpoint,
        headers=_headers(admin),
        json={**scope, "status": "cancelled", "expected_version": 3},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["lifecycle_version"] == 4
    terminal_change = client.patch(
        endpoint,
        headers=_headers(admin),
        json={**scope, "status": "processing", "expected_version": 4},
    )
    assert terminal_change.status_code == 409
    assert terminal_change.json()["detail"]["code"] == (
        "invalid_service_request_transition"
    )
    unsupported = client.patch(
        endpoint,
        headers=_headers(admin),
        json={**scope, "status": "teleported", "expected_version": 4},
    )
    assert unsupported.status_code == 422

    db_session.expire_all()
    persisted = db_session.get(MobileServiceRequest, request["id"])
    assert persisted is not None
    assert (
        persisted.status,
        persisted.progress_percent,
        persisted.lifecycle_version,
    ) == (
        "cancelled",
        50,
        4,
    )
    with pytest.raises(IntegrityError):
        db_session.execute(
            update(MobileServiceRequest)
            .where(MobileServiceRequest.id == request["id"])
            .values(status="teleported")
        )
        db_session.commit()
    db_session.rollback()
    with pytest.raises(IntegrityError):
        db_session.execute(
            update(MobileServiceRequest)
            .where(MobileServiceRequest.id == request["id"])
            .values(progress_percent=101)
        )
        db_session.commit()
    db_session.rollback()


def test_keyed_service_request_replays_after_legacy_site_deletion(
    client,
    db_session,
):
    owner = _user(db_session, "deleted-site-replay-owner")
    _, workspace_id = _organization(
        client,
        owner,
        f"Deleted site replay {uuid.uuid4().hex[:8]}",
    )
    headers = _headers(owner, workspace_id)
    site = client.post(
        "/mobile/sites",
        headers=headers,
        json={
            "name": "Ephemeral legacy site",
            "sector": "agro",
            "country": "Angola",
            "province": "Huambo",
            "municipality": "Caala",
        },
    )
    assert site.status_code == 201, site.text
    request_body = {
        "site_id": site.json()["id"],
        "site_name": site.json()["name"],
        "type": "drone_inspection",
        "urgency": "normal",
        "description": "Replay this committed request after Site deletion.",
        "attachments": [],
    }
    key = f"deleted-site-replay-{uuid.uuid4()}"
    created = client.post(
        "/mobile/service-requests",
        headers={**headers, "Idempotency-Key": key},
        json=request_body,
    )
    assert created.status_code == 201, created.text

    site_row = db_session.get(Site, site.json()["id"])
    assert site_row is not None
    archive_legacy_asset(db_session, source="site", source_id=site_row.id)
    db_session.delete(site_row)
    db_session.commit()

    replay = client.post(
        "/mobile/service-requests",
        headers={**headers, "Idempotency-Key": key},
        json=request_body,
    )
    assert replay.status_code == 200, replay.text
    assert replay.headers["idempotency-replayed"] == "true"
    assert replay.json()["id"] == created.json()["id"]

    conflict = client.post(
        "/mobile/service-requests",
        headers={**headers, "Idempotency-Key": key},
        json={**request_body, "description": "Different replay payload."},
    )
    assert conflict.status_code == 409, conflict.text


def test_phase33_contractor_surface_is_job_scoped_and_redacted(
    client,
    db_session,
):
    admin = db_session.query(User).filter(User.email == "teste@admin.com").one()
    admin_headers = _headers(admin)
    assigned_user = _user(db_session, "assigned-contractor")
    unrelated_user = _user(db_session, "unrelated-contractor")
    suffix = uuid.uuid4().hex[:12]

    def contractor(user: User, label: str) -> dict:
        response = client.post(
            "/operations/contractors",
            headers=admin_headers,
            json={
                "code": f"PHASE33_{label.upper()}_{suffix}",
                "user_id": user.id,
                "display_name": f"{label.title()} contractor",
                "resource_type": "PILOT",
                "country_code": "AO",
                "internal_notes": f"private-{label}-commercial-rating",
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    assigned = contractor(assigned_user, "assigned")
    unrelated = contractor(unrelated_user, "unrelated")

    def assignment(contractor_id: str, label: str) -> dict:
        response = client.post(
            "/operations/assignments",
            headers=admin_headers,
            json={
                "contractor_id": contractor_id,
                "title": f"{label.title()} field job",
                "location": {
                    "name": f"{label.title()} field",
                    "customer_email": f"private-{label}@example.com",
                    "provider_reference": f"provider-{label}",
                },
                "requirements": {
                    "capabilities": ["RGB"],
                    "customer_id": f"customer-{label}",
                    "provider_code": f"provider-{label}",
                },
                "upload_area": {
                    "method": "platform-upload",
                    "provider_container": f"private-container-{label}",
                },
                "agreed_cost_amount": 125_000,
                "cost_currency": "AOA",
                "internal_notes": f"private-margin-{label}",
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    own_job = assignment(assigned["id"], "assigned")
    other_job = assignment(unrelated["id"], "unrelated")
    contractor_headers = _headers(assigned_user)
    own = client.get(
        "/operations/contractor/me/assignments", headers=contractor_headers
    )
    assert own.status_code == 200, own.text
    assert [row["id"] for row in own.json()] == [own_job["id"]]
    serialized = own.text
    for private_value in (
        "private-assigned@example.com",
        "provider-assigned",
        "customer-assigned",
        "private-container-assigned",
        "private-margin-assigned",
    ):
        assert private_value not in serialized
    assert {
        "contractor_id",
        "order_id",
        "fulfilment_job_id",
        "agreed_cost_amount",
        "cost_currency",
        "internal_notes",
        "assigned_by_user_id",
    }.isdisjoint(own.json()[0])
    hidden_job = client.get(
        f"/operations/contractor/me/assignments/{other_job['id']}",
        headers=contractor_headers,
    )
    assert hidden_job.status_code == 404
    assert (
        client.get("/operations/assignments", headers=contractor_headers).status_code
        == 403
    )
