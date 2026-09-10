from __future__ import annotations

import hashlib
import json
import uuid
from datetime import timedelta

from app.core.time import utc_now
from app.core.tokens import create_user_access_token
from app.models import (
    Account,
    Asset,
    AuditLog,
    Company,
    ContractorAssignment,
    ContractorCapability,
    Dataset,
    DatasetFile,
    FulfilmentJob,
    IntegrationOutbox,
    InternalRoleAssignment,
    OperationalCapability,
    OperationalDomainEvent,
    OperationsContractor,
    Order,
    ProcessingJob,
    Report,
    User,
)
from app.integrations.storage.local import LocalObjectStorageProvider
from app.services.storage import StorageService


def _headers(user: User) -> dict[str, str]:
    token = create_user_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        auth_generation=user.auth_generation,
    )
    return {"Authorization": f"Bearer {token}"}


def _staff(db_session, role: str) -> User:
    user = User(
        email=f"phase24-{role.lower()}-{uuid.uuid4().hex}@example.test",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(InternalRoleAssignment(user_id=user.id, role=role))
    db_session.commit()
    return user


def _contractor_fixture(db_session):
    suffix = uuid.uuid4().hex[:10]
    contractor_user = User(
        email=f"phase24-contractor-{suffix}@example.test",
        role="client",
        is_active=True,
    )
    other_user = User(
        email=f"phase24-other-{suffix}@example.test",
        role="client",
        is_active=True,
    )
    organization = Company(
        name=f"Phase 24 customer {suffix}",
        email=f"phase24-org-{suffix}@example.test",
        status="active",
    )
    db_session.add_all([contractor_user, other_user, organization])
    db_session.flush()
    workspace = Account(
        organization_id=organization.id,
        name=f"Phase 24 workspace {suffix}",
        sector_focus="agriculture",
        entity_type="organization",
        customer_type="farm",
        dashboard_profile="farm",
        modules_enabled='["assets","services"]',
        status="active",
    )
    db_session.add(workspace)
    db_session.flush()
    asset = Asset(
        organization_id=organization.id,
        workspace_id=workspace.id,
        sector="AGRICULTURE",
        asset_type="FARM",
        name=f"Assigned field {suffix}",
        location_label="Bengo field entrance",
        geometry_geojson='{"type":"Point","coordinates":[13.23,-8.84]}',
        status="active",
    )
    order = Order(
        user_id=contractor_user.id,
        company_id=organization.id,
        organization_id=organization.id,
        workspace_id=workspace.id,
        order_number=f"GV-2026-{suffix.upper()}",
        order_type="SERVICE",
        status="paid",
        fulfilment_status="PAID",
        payment_status="PAID",
        currency="AOA",
        subtotal=950_000,
        total=1_000_000,
        internal_notes="Customer margin is private",
    )
    contractor = OperationsContractor(
        code=f"PHASE24_{suffix.upper()}",
        user_id=contractor_user.id,
        display_name="Assigned field contractor",
        legal_name="Private contractor legal name",
        resource_type="FIELD_TECHNICIAN",
        status="ACTIVE",
        availability="AVAILABLE",
        contact_email=contractor_user.email,
        region="Bengo",
        service_area_json='["Bengo"]',
        certifications_json='[{"type":"field_safety","status":"VALID"}]',
        equipment_json='[{"type":"thermal_camera"}]',
        document_refs_json=(
            '[{"document_id":"staff-vetted-doc","status":"VERIFIED",'
            '"reviewer":"operations"}]'
        ),
        quality_score=97,
        internal_notes="Internal performance and rate notes",
    )
    other_contractor = OperationsContractor(
        code=f"PHASE24_OTHER_{suffix.upper()}",
        user_id=other_user.id,
        display_name="Unrelated contractor",
        resource_type="FIELD_TECHNICIAN",
        status="ACTIVE",
        availability="AVAILABLE",
    )
    db_session.add_all([asset, order, contractor, other_contractor])
    db_session.flush()
    capability = (
        db_session.query(OperationalCapability)
        .filter(OperationalCapability.code == "PHASE24_THERMAL")
        .one_or_none()
    )
    if capability is None:
        capability = OperationalCapability(
            code="PHASE24_THERMAL",
            name="Phase 24 thermal capture",
            category="SENSOR",
            is_active=True,
        )
        db_session.add(capability)
        db_session.flush()
    db_session.add(
        ContractorCapability(
            contractor_id=contractor.id,
            capability_id=capability.id,
            proficiency="QUALIFIED",
        )
    )
    dataset = Dataset(
        company_id=organization.id,
        workspace_id=workspace.id,
        asset_id=asset.id,
        name="Authorized field evidence",
        dataset_type="RGB_IMAGES",
        processing_level="RAW",
        quality_status="UNREVIEWED",
        status="uploading",
        file_count=0,
        total_size_bytes=0,
        created_by_user_id=contractor_user.id,
    )
    unrelated_dataset = Dataset(
        company_id=organization.id,
        workspace_id=workspace.id,
        asset_id=asset.id,
        name="Different job evidence",
        dataset_type="THERMAL_IMAGES",
        processing_level="RAW",
        quality_status="UNREVIEWED",
        status="uploading",
        file_count=0,
        total_size_bytes=0,
        created_by_user_id=other_user.id,
    )
    job = FulfilmentJob(
        job_number=f"GVJ-2026-{suffix.upper()}",
        order_id=order.id,
        asset_id=asset.id,
        job_type="FLIGHT_CAPTURE",
        title="Capture assigned field evidence",
        priority="HIGH",
        state="ASSIGNED",
        assigned_contractor_id=contractor.id,
        requirements_json=json.dumps(
            {
                "capabilities": ["PHASE24_THERMAL"],
                "equipment": ["thermal_camera"],
                "safety_briefing": True,
                "customer_name": "must be removed",
                "internal_notes": "must be removed",
                "margin": 40,
                "provider_job_reference": "provider-private-123",
                "reviewer": "staff-reviewer",
                "hourly_rate": 9_999,
            }
        ),
        direct_cost_amount=400_000,
        cost_currency="AOA",
        cost_reference="private-rate-card",
        lifecycle_version=1,
        created_by_user_id=contractor_user.id,
    )
    other_job = FulfilmentJob(
        job_number=f"GVJ-2026-OTHER-{suffix.upper()}",
        order_id=order.id,
        asset_id=asset.id,
        job_type="FLIGHT_CAPTURE",
        title="Different assigned work",
        priority="NORMAL",
        state="ASSIGNED",
        assigned_contractor_id=contractor.id,
        requirements_json="{}",
        lifecycle_version=1,
        created_by_user_id=contractor_user.id,
    )
    db_session.add_all([dataset, unrelated_dataset, job, other_job])
    db_session.flush()
    assignment = ContractorAssignment(
        assignment_number=f"GVA-2026-{suffix.upper()}",
        contractor_id=contractor.id,
        order_id=order.id,
        fulfilment_job_id=job.id,
        title="Assigned field mission",
        status="OFFERED",
        window_start=utc_now() + timedelta(days=1),
        window_end=utc_now() + timedelta(days=1, hours=4),
        location_json=json.dumps(
            {
                "name": "Bengo field entrance",
                "latitude": -8.84,
                "longitude": 13.23,
                "customer_contact": "must be removed",
            }
        ),
        requirements_json=json.dumps(
            {
                "equipment": ["thermal_camera"],
                "internal_rate": 200,
            }
        ),
        upload_area_json=json.dumps(
            {"method": "platform-upload", "dataset_id": dataset.id}
        ),
        required_documents_json=(
            '[{"type":"insurance","status":"VALID",'
            '"reviewer_user_id":"must be removed"}]'
        ),
        agreed_cost_amount=400_000,
        cost_currency="AOA",
        internal_notes="Private margin and customer information",
        lifecycle_version=1,
    )
    other_assignment = ContractorAssignment(
        assignment_number=f"GVA-2026-OTHER-{suffix.upper()}",
        contractor_id=contractor.id,
        order_id=order.id,
        fulfilment_job_id=other_job.id,
        title="Different accepted mission",
        status="ACCEPTED",
        location_json="{}",
        requirements_json="{}",
        upload_area_json=json.dumps(
            {"method": "platform-upload", "dataset_id": unrelated_dataset.id}
        ),
        required_documents_json="[]",
        lifecycle_version=1,
        accepted_at=utc_now(),
    )
    db_session.add_all([assignment, other_assignment])
    db_session.commit()
    return {
        "user": contractor_user,
        "other_user": other_user,
        "contractor": contractor,
        "other_contractor": other_contractor,
        "organization": organization,
        "workspace": workspace,
        "asset": asset,
        "order": order,
        "dataset": dataset,
        "unrelated_dataset": unrelated_dataset,
        "job": job,
        "other_job": other_job,
        "assignment": assignment,
    }


def test_internal_experience_is_role_driven_and_erp_queue_is_finance_scoped(
    client, db_session
):
    finance = _staff(db_session, "GV_FINANCE")
    analyst = _staff(db_session, "GV_ANALYST")
    support = _staff(db_session, "GV_SUPPORT")
    operations = _staff(db_session, "GV_OPERATIONS")
    super_admin = _staff(db_session, "GV_SUPER_ADMIN")
    customer = User(
        email=f"phase24-customer-{uuid.uuid4().hex}@example.test",
        role="client",
        is_active=True,
    )
    organization = Company(
        name=f"Phase 24 queue {uuid.uuid4().hex[:8]}",
        email=f"phase24-queue-{uuid.uuid4().hex}@example.test",
        status="active",
    )
    db_session.add_all([customer, organization])
    db_session.flush()
    workspace = Account(
        organization_id=organization.id,
        name="Phase 24 queue workspace",
        sector_focus="infrastructure",
        entity_type="organization",
        customer_type="company",
        dashboard_profile="infrastructure",
        modules_enabled='["assets","reports"]',
        status="active",
    )
    db_session.add(workspace)
    db_session.flush()
    asset = Asset(
        organization_id=organization.id,
        workspace_id=workspace.id,
        sector="INFRASTRUCTURE",
        asset_type="CONSTRUCTION_SITE",
        name="Phase 24 review asset",
        status="active",
    )
    db_session.add(asset)
    db_session.flush()
    report = Report(
        organization_id=organization.id,
        workspace_id=workspace.id,
        asset_id=asset.id,
        report_type="PROGRESS",
        title="Phase 24 report awaiting review",
        template_version="1",
        revision=1,
        status="REVIEW_REQUIRED",
        qa_level="HUMAN_REVIEW",
        context_schema_version="1",
        context_json="{}",
        context_sha256="0" * 64,
        narrative_provider="deterministic",
        narrative_schema_version="1",
        narrative_json="{}",
        qa_result_json="{}",
        generation_key=f"phase24-report-{uuid.uuid4()}",
        lifecycle_version=2,
    )
    processing = ProcessingJob(
        organization_id=organization.id,
        provider_code="private-provider-code",
        provider_job_reference="private-provider-reference",
        requested_outputs_json='["ORTHOMOSAIC"]',
        options_json='{"provider_secret":"must-not-leak"}',
        status="FAILED",
        stage="provider_poll",
        estimated_cost_amount=500,
        actual_cost_amount=450,
        cost_currency="USD",
        error_code="provider_timeout",
        error_message="Authorization: Bearer very-secret-token",
        retry_count=2,
        max_retries=3,
        poll_count=4,
        submission_generation=1,
        idempotency_key=f"phase24-processing-{uuid.uuid4()}",
        lifecycle_version=1,
    )
    finance_outbox = IntegrationOutbox(
        company_id=organization.id,
        provider="odoo",
        aggregate_type="order",
        aggregate_id=f"order-{uuid.uuid4()}",
        event_type="order.status",
        payload_json='{"amount":1000}',
        idempotency_key=f"phase24-finance-{uuid.uuid4()}",
        status="dead_letter",
        attempts=3,
        max_attempts=3,
        last_error_code="terminal",
        last_error="api_key=very-secret-key",
    )
    non_finance_outbox = IntegrationOutbox(
        company_id=organization.id,
        provider="external-gis",
        aggregate_type="dataset",
        aggregate_id=f"dataset-{uuid.uuid4()}",
        event_type="dataset.status",
        payload_json='{"private":"payload"}',
        idempotency_key=f"phase24-non-finance-{uuid.uuid4()}",
        status="dead_letter",
        attempts=2,
        max_attempts=4,
        last_error_code="terminal",
        last_error="Bearer another-secret-token",
    )
    db_session.add_all([report, processing, finance_outbox, non_finance_outbox])
    db_session.commit()

    finance_experience = client.get(
        "/operations/experience", headers=_headers(finance)
    )
    assert finance_experience.status_code == 200, finance_experience.text
    assert finance_experience.json()["capabilities"] == [
        "dashboard",
        "orders",
        "finance_sync",
    ]
    assert [row["key"] for row in finance_experience.json()["navigation"]] == [
        "dashboard",
        "orders",
        "finance_sync",
    ]
    finance_queues = client.get("/operations/queues", headers=_headers(finance))
    assert finance_queues.status_code == 200, finance_queues.text
    finance_ids = {row["id"] for row in finance_queues.json()["integrations"]}
    assert finance_outbox.id in finance_ids
    assert non_finance_outbox.id not in finance_ids
    finance_item = next(
        row
        for row in finance_queues.json()["integrations"]
        if row["id"] == finance_outbox.id
    )
    assert "very-secret-key" not in finance_item["error_message"]
    assert finance_queues.json()["jobs"] == []
    assert finance_queues.json()["processing"] == []
    finance_dashboard = client.get(
        "/operations/dashboard", headers=_headers(finance)
    )
    assert finance_dashboard.status_code == 200, finance_dashboard.text
    assert finance_dashboard.json()["attention"]["dead_letter_integrations"] >= 1
    assert finance_dashboard.json()["health"] is None

    analyst_nav = client.get(
        "/operations/experience", headers=_headers(analyst)
    ).json()["capabilities"]
    assert analyst_nav == ["dashboard", "assets", "missions", "reports_qa"]
    analyst_queues = client.get(
        "/operations/queues", headers=_headers(analyst)
    )
    assert analyst_queues.status_code == 200, analyst_queues.text
    report_item = next(
        row
        for row in analyst_queues.json()["reports_qa"]
        if row["id"] == report.id
    )
    assert report_item["lifecycle_version"] == 2
    support_nav = client.get(
        "/operations/experience", headers=_headers(support)
    ).json()["capabilities"]
    assert support_nav == ["dashboard", "organizations", "assets", "system_health"]
    support_health = client.get(
        "/operations/dashboard", headers=_headers(support)
    ).json()["health"]
    assert support_health["processing_failures"] >= 1
    assert support_health["integration_dead_letters"] >= 2
    operations_queues = client.get(
        "/operations/queues", headers=_headers(operations)
    )
    assert operations_queues.status_code == 200, operations_queues.text
    processing_item = next(
        row
        for row in operations_queues.json()["processing"]
        if row["id"] == processing.id
    )
    assert processing_item["retry_count"] == 2
    assert processing_item["max_retries"] == 3
    assert processing_item["retries_remaining"] == 1
    assert "very-secret-token" not in processing_item["error_message"]
    assert "provider_code" not in processing_item
    assert "provider_job_reference" not in processing_item
    assert "cost" not in json.dumps(processing_item).lower()

    admin_experience = client.get(
        "/operations/experience", headers=_headers(super_admin)
    )
    assert admin_experience.status_code == 200, admin_experience.text
    assert admin_experience.json()["capabilities"] == [
        "dashboard",
        "organizations",
        "assets",
        "orders",
        "jobs",
        "missions",
        "processing",
        "reports_qa",
        "contractors",
        "inventory",
        "finance_sync",
        "integrations",
        "system_health",
    ]
    admin_queue_ids = {
        row["id"]
        for row in client.get(
            "/operations/queues", headers=_headers(super_admin)
        ).json()["integrations"]
    }
    assert {finance_outbox.id, non_finance_outbox.id}.issubset(admin_queue_ids)

    assert client.get("/operations/experience", headers=_headers(customer)).status_code == 403
    assert client.get("/operations/dashboard", headers=_headers(customer)).status_code == 403
    assert client.get("/operations/queues", headers=_headers(customer)).status_code == 403


def test_contractor_job_lifecycle_is_assignment_gated_audited_and_private(
    client, db_session
):
    data = _contractor_fixture(db_session)
    headers = _headers(data["user"])
    other_headers = _headers(data["other_user"])

    offered_detail = client.get(
        f"/operations/contractor/me/jobs/{data['job'].id}", headers=headers
    )
    assert offered_detail.status_code == 200, offered_detail.text
    assert offered_detail.json()["allowed_transitions"] == []
    offered_transition = client.patch(
        f"/operations/contractor/me/jobs/{data['job'].id}/state",
        headers=headers,
        json={"state": "IN_PROGRESS", "expected_version": 1},
    )
    assert offered_transition.status_code == 409, offered_transition.text
    assert offered_transition.json()["detail"]["code"] == "accepted_assignment_required"

    accepted = client.post(
        f"/operations/contractor/me/assignments/{data['assignment'].id}/decision",
        headers=headers,
        json={"decision": "ACCEPTED", "expected_version": 1},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "ACCEPTED"
    db_session.expire_all()
    accepted_job = db_session.get(FulfilmentJob, data["job"].id)
    assert accepted_job.assigned_contractor_id == data["contractor"].id
    assert accepted_job.state == "SCHEDULED"
    assert accepted_job.scheduled_start == data["assignment"].window_start
    assert accepted_job.scheduled_end == data["assignment"].window_end
    assert (
        db_session.query(AuditLog)
        .filter(
            AuditLog.resource_id == data["job"].id,
            AuditLog.action == "operations.job.assignment_changed",
        )
        .count()
        == 1
    )
    assert (
        db_session.query(OperationalDomainEvent)
        .filter(
            OperationalDomainEvent.aggregate_id == data["job"].id,
            OperationalDomainEvent.event_type == "fulfilment_job.assignment_changed",
        )
        .count()
        == 1
    )
    assert (
        db_session.query(OperationalDomainEvent)
        .filter(
            OperationalDomainEvent.aggregate_id == data["job"].id,
            OperationalDomainEvent.event_type == "fulfilment_job.schedule_changed",
        )
        .count()
        == 1
    )

    job_version_after_accept = accepted_job.lifecycle_version
    repeated_accept = client.post(
        f"/operations/contractor/me/assignments/{data['assignment'].id}/decision",
        headers=headers,
        json={
            "decision": "ACCEPTED",
            "expected_version": accepted.json()["lifecycle_version"],
        },
    )
    assert repeated_accept.status_code == 200, repeated_accept.text
    db_session.expire_all()
    assert db_session.get(FulfilmentJob, data["job"].id).lifecycle_version == (
        job_version_after_accept
    )
    assert (
        db_session.query(OperationalDomainEvent)
        .filter(
            OperationalDomainEvent.aggregate_id == data["job"].id,
            OperationalDomainEvent.event_type.in_(
                (
                    "fulfilment_job.assignment_changed",
                    "fulfilment_job.schedule_changed",
                )
            ),
        )
        .count()
        == 2
    )

    # A later duplicate offer cannot shadow the durable accepted assignment.
    duplicate_offer = ContractorAssignment(
        assignment_number=f"GVA-2026-DUP-{uuid.uuid4().hex[:10].upper()}",
        contractor_id=data["contractor"].id,
        order_id=data["order"].id,
        fulfilment_job_id=data["job"].id,
        title="Later duplicate offer",
        status="OFFERED",
        location_json="{}",
        requirements_json="{}",
        upload_area_json="{}",
        required_documents_json="[]",
        lifecycle_version=1,
    )
    db_session.add(duplicate_offer)
    db_session.commit()

    detail = client.get(
        f"/operations/contractor/me/jobs/{data['job'].id}", headers=headers
    )
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert payload["allowed_transitions"] == ["IN_PROGRESS"]
    assert payload["assignment"]["id"] == data["assignment"].id
    assert payload["assignment"]["status"] == "ACCEPTED"
    assert payload["location"]["name"] == "Bengo field entrance"
    assert payload["upload_targets"] == [
        {
            "dataset_id": data["dataset"].id,
            "name": "Authorized field evidence",
            "status": "uploading",
            "file_count": 0,
        }
    ]
    serialized = detail.text.lower()
    for private_name in (
        "order_id",
        "asset_id",
        "organization_id",
        "workspace_id",
        "customer_name",
        "customer_contact",
        "direct_cost",
        "cost_currency",
        "cost_reference",
        "internal_notes",
        "internal_rate",
        "margin",
        "assigned_contractor_id",
        "assigned_user_id",
        "provider_job_reference",
        "reviewer",
        "hourly_rate",
    ):
        assert private_name not in serialized
    my_jobs = client.get("/operations/contractor/me/jobs", headers=headers)
    assert my_jobs.status_code == 200, my_jobs.text
    for private_name in ("provider_job_reference", "reviewer", "hourly_rate"):
        assert private_name not in my_jobs.text

    started = client.patch(
        f"/operations/contractor/me/jobs/{data['job'].id}/state",
        headers=headers,
        json={
            "state": "IN_PROGRESS",
            "expected_version": payload["lifecycle_version"],
        },
    )
    assert started.status_code == 200, started.text
    assert started.json()["state"] == "IN_PROGRESS"
    assert started.json()["allowed_transitions"] == ["WAITING_INPUT", "QA_REVIEW"]
    state_audits = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.resource_id == data["job"].id,
            AuditLog.action == "operations.job.state_changed",
        )
        .count()
    )
    assert state_audits == 1

    assert (
        client.get(
            f"/operations/contractor/me/jobs/{data['job'].id}",
            headers=other_headers,
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/operations/contractor/me/jobs/{data['job'].id}/state",
            headers=other_headers,
            json={"state": "QA_REVIEW"},
        ).status_code
        == 404
    )
    assert client.get("/operations/dashboard", headers=headers).status_code == 403


def test_cancelling_accepted_assignment_revokes_linked_job_access(client, db_session):
    data = _contractor_fixture(db_session)
    contractor_headers = _headers(data["user"])
    operations_headers = _headers(_staff(db_session, "GV_OPERATIONS"))

    accepted = client.post(
        f"/operations/contractor/me/assignments/{data['assignment'].id}/decision",
        headers=contractor_headers,
        json={"decision": "ACCEPTED", "expected_version": 1},
    )
    assert accepted.status_code == 200, accepted.text
    cancelled = client.patch(
        f"/operations/assignments/{data['assignment'].id}",
        headers=operations_headers,
        json={
            "status": "CANCELLED",
            "expected_version": accepted.json()["lifecycle_version"],
        },
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"
    db_session.expire_all()
    job = db_session.get(FulfilmentJob, data["job"].id)
    assert job.assigned_contractor_id is None
    assert job.state == "READY"
    assert job.scheduled_start is None and job.scheduled_end is None
    assert (
        client.get(
            f"/operations/contractor/me/jobs/{job.id}", headers=contractor_headers
        ).status_code
        == 404
    )
    visible_jobs = client.get(
        "/operations/contractor/me/jobs", headers=contractor_headers
    )
    assert visible_jobs.status_code == 200, visible_jobs.text
    assert job.id not in {row["id"] for row in visible_jobs.json()}


def test_contractor_upload_receipt_is_exact_non_replayable_and_idempotent(
    client, db_session, monkeypatch, tmp_path
):
    storage = StorageService(
        LocalObjectStorageProvider(
            root=tmp_path / "phase24-objects",
            public_base_url="http://testserver/datasets/storage/local",
            signing_secret="phase24-test-signing-secret",
        )
    )
    monkeypatch.setattr(
        "app.routers.fulfilment_jobs.get_storage_service",
        lambda: storage,
    )
    data = _contractor_fixture(db_session)
    headers = _headers(data["user"])
    other_headers = _headers(data["other_user"])
    data["assignment"].status = "ACCEPTED"
    data["assignment"].accepted_at = utc_now()
    db_session.commit()

    content = b"phase-24-authorized-evidence"
    initiated = client.post(
        f"/operations/contractor/me/jobs/{data['job'].id}/uploads/initiate",
        headers=headers,
        json={
            "dataset_id": data["dataset"].id,
            "filename": "field-evidence.jpg",
            "content_type": "image/jpeg",
            "size_bytes": len(content),
            "object_area": "raw",
        },
    )
    assert initiated.status_code == 201, initiated.text
    initiation = initiated.json()
    assert set(initiation) == {
        "upload_url",
        "upload_reference",
        "expires_in",
        "required_headers",
    }
    assert "storage_key" not in initiated.text
    upload_reference = initiation["upload_reference"]

    assignment_projection = client.get(
        f"/operations/contractor/me/assignments/{data['assignment'].id}",
        headers=headers,
    )
    assert assignment_projection.status_code == 200, assignment_projection.text
    restricted_assignment = assignment_projection.json()
    assert restricted_assignment["location"]["name"] == "Bengo field entrance"
    assert restricted_assignment["requirements"]["equipment"] == ["thermal_camera"]
    assert restricted_assignment["required_documents"][0]["status"] == "VALID"
    assert restricted_assignment["document_profile"][0]["status"] == "VERIFIED"
    for private_key in (
        "reservations",
        "created_by_user_id",
        "customer_contact",
        "internal_rate",
        "reviewer_user_id",
        "reviewer",
    ):
        assert private_key not in assignment_projection.text
    assignment_list = client.get(
        "/operations/contractor/me/assignments", headers=headers
    )
    assert assignment_list.status_code == 200, assignment_list.text
    for private_key in (
        "customer_contact",
        "internal_rate",
        "reviewer_user_id",
        "reviewer",
    ):
        assert private_key not in assignment_list.text

    guessed_by_other = client.post(
        f"/operations/contractor/me/jobs/{data['job'].id}/uploads/complete",
        headers=other_headers,
        json={
            "dataset_id": data["dataset"].id,
            "upload_reference": upload_reference,
            "size_bytes": len(content),
        },
    )
    assert guessed_by_other.status_code == 404
    replayed_on_other_job = client.post(
        f"/operations/contractor/me/jobs/{data['other_job'].id}/uploads/complete",
        headers=headers,
        json={
            "dataset_id": data["unrelated_dataset"].id,
            "upload_reference": upload_reference,
            "size_bytes": len(content),
        },
    )
    assert replayed_on_other_job.status_code == 404, replayed_on_other_job.text
    assert replayed_on_other_job.json()["detail"]["code"] == "upload_reference_not_found"

    reserved = db_session.get(DatasetFile, upload_reference)
    assert reserved is not None and reserved.storage_key
    contractor = db_session.get(OperationsContractor, data["contractor"].id)
    contractor.status = "ON_HOLD"
    db_session.commit()
    suspended_transfer = client.put(
        initiation["upload_url"],
        content=content,
        headers=initiation["required_headers"],
    )
    assert suspended_transfer.status_code == 404, suspended_transfer.text
    contractor.status = "ACTIVE"
    db_session.commit()
    transferred = client.put(
        initiation["upload_url"],
        content=content,
        headers=initiation["required_headers"],
    )
    assert transferred.status_code == 204, transferred.text
    checksum = hashlib.sha256(content).hexdigest()
    complete_payload = {
        "dataset_id": data["dataset"].id,
        "upload_reference": upload_reference,
        "size_bytes": len(content),
        "sha256_hash": checksum,
    }
    completed = client.post(
        f"/operations/contractor/me/jobs/{data['job'].id}/uploads/complete",
        headers=headers,
        json=complete_payload,
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["upload_reference"] == upload_reference
    assert completed.json()["dataset_id"] == data["dataset"].id
    assert completed.json()["status"] == "uploaded"

    confirmed_audits = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.resource_id == data["job"].id,
            AuditLog.action == "operations.job.upload_confirmed",
        )
        .count()
    )
    repeated = client.post(
        f"/operations/contractor/me/jobs/{data['job'].id}/uploads/complete",
        headers=headers,
        json=complete_payload,
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == completed.json()
    assert (
        db_session.query(AuditLog)
        .filter(
            AuditLog.resource_id == data["job"].id,
            AuditLog.action == "operations.job.upload_confirmed",
        )
        .count()
        == confirmed_audits
        == 1
    )
    mismatched_size = client.post(
        f"/operations/contractor/me/jobs/{data['job'].id}/uploads/complete",
        headers=headers,
        json={**complete_payload, "size_bytes": len(content) + 1},
    )
    assert mismatched_size.status_code == 422, mismatched_size.text
    assert mismatched_size.json()["detail"]["code"] == "upload_mismatch"
    mismatched_checksum = client.post(
        f"/operations/contractor/me/jobs/{data['job'].id}/uploads/complete",
        headers=headers,
        json={**complete_payload, "sha256_hash": "0" * 64},
    )
    assert mismatched_checksum.status_code == 422, mismatched_checksum.text
    assert mismatched_checksum.json()["detail"]["code"] == "upload_mismatch"

    # Cloud-style provider metadata is authoritative for content type. A client
    # cannot reserve an image and upload executable/browser content instead.
    storage.provider.provider_name = "azure_blob"
    hostile_content = b"<script>alert('phase24')</script>"
    hostile_initiated = client.post(
        f"/operations/contractor/me/jobs/{data['job'].id}/uploads/initiate",
        headers=headers,
        json={
            "dataset_id": data["dataset"].id,
            "filename": "hostile.jpg",
            "content_type": "image/jpeg",
            "size_bytes": len(hostile_content),
        },
    )
    assert hostile_initiated.status_code == 201, hostile_initiated.text
    hostile_file = db_session.get(
        DatasetFile, hostile_initiated.json()["upload_reference"]
    )
    storage.upload_bytes(
        hostile_content,
        hostile_file.storage_key,
        "text/html",
    )
    original_stat = storage.stat_file

    def cloud_stat(storage_key):
        info = original_stat(storage_key)
        if storage_key == hostile_file.storage_key and info is not None:
            return {**info, "content_type": "text/html"}
        return info

    monkeypatch.setattr(storage, "stat_file", cloud_stat)
    hostile_complete = client.post(
        f"/operations/contractor/me/jobs/{data['job'].id}/uploads/complete",
        headers=headers,
        json={
            "dataset_id": data["dataset"].id,
            "upload_reference": hostile_file.id,
            "size_bytes": len(hostile_content),
        },
    )
    assert hostile_complete.status_code == 422, hostile_complete.text
    assert hostile_complete.json()["detail"]["code"] == "file_type_not_allowed"
    assert storage.file_exists(hostile_file.storage_key) is False


def test_contractor_profile_updates_cannot_spoof_staff_vetting(client, db_session):
    data = _contractor_fixture(db_session)
    headers = _headers(data["user"])

    spoofed = client.patch(
        "/operations/contractor/me/profile",
        headers=headers,
        json={
            "document_refs": [
                {
                    "document_id": "spoofed",
                    "status": "VERIFIED",
                    "reviewer": "self",
                    "url": "https://attacker.invalid/document",
                }
            ]
        },
    )
    assert spoofed.status_code == 422, spoofed.text
    db_session.expire_all()
    contractor = db_session.get(OperationsContractor, data["contractor"].id)
    assert "staff-vetted-doc" in contractor.document_refs_json
    assert "spoofed" not in contractor.document_refs_json

    updated = client.patch(
        "/operations/contractor/me/profile",
        headers=headers,
        json={
            "availability": "LIMITED",
            "region": "Luanda and Bengo",
            "service_area": ["Bengo", {"region": "Luanda", "radius_km": 80}],
            "equipment": [{"type": "thermal_camera", "serial": "GV-OWNED-1"}],
        },
    )
    assert updated.status_code == 200, updated.text
    profile = updated.json()
    assert profile["availability"] == "LIMITED"
    assert profile["document_refs"][0]["status"] == "VERIFIED"
    assert "reviewer" not in updated.text
    assert "internal_notes" not in profile
    assert "quality_score" not in profile

    experience = client.get(
        "/operations/contractor/me/experience", headers=headers
    )
    assert experience.status_code == 200, experience.text
    assert experience.json()["surface"] == "CONTRACTOR"
    assert experience.json()["capabilities"] == [
        "my_jobs",
        "job_status",
        "uploads",
        "profile",
        "documents",
    ]
    assert "legal_name" not in experience.text
    assert "internal" not in experience.text.lower()

    contractor.status = "ON_HOLD"
    db_session.commit()
    for method, path, payload in (
        ("get", "/operations/contractor/me/experience", None),
        ("get", "/operations/contractor/me/jobs", None),
        (
            "patch",
            "/operations/contractor/me/profile",
            {"availability": "AVAILABLE"},
        ),
    ):
        request_kwargs = {"headers": headers}
        if payload is not None:
            request_kwargs["json"] = payload
        response = client.request(method.upper(), path, **request_kwargs)
        assert response.status_code == 403, response.text
        assert response.json()["detail"]["code"] == "contractor_access_denied"


def test_phase_24_openapi_uses_explicit_operations_contracts(client):
    schema = client.app.openapi()
    paths = schema["paths"]
    expected = {
        ("/operations/experience", "get", "OperationsExperienceOut"),
        ("/operations/dashboard", "get", "OperationsDashboardOut"),
        ("/operations/queues", "get", "OperationsQueuesOut"),
        (
            "/operations/contractor/me/experience",
            "get",
            "ContractorExperienceOut",
        ),
        (
            "/operations/contractor/me/jobs/{job_id}",
            "get",
            "ContractorJobDetailOut",
        ),
        (
            "/operations/contractor/me/jobs/{job_id}/state",
            "patch",
            "ContractorJobDetailOut",
        ),
        (
            "/operations/contractor/me/jobs/{job_id}/uploads/initiate",
            "post",
            "ContractorUploadInitiatedOut",
        ),
        (
            "/operations/contractor/me/jobs/{job_id}/uploads/complete",
            "post",
            "ContractorUploadReceiptOut",
        ),
    }
    for path, method, model in expected:
        assert paths[path][method]["responses"]["200" if method != "post" else (
            "201" if path.endswith("initiate") else "200"
        )]["content"]["application/json"]["schema"]["$ref"].endswith(model)

    assert "204" in paths["/operations/contractor/uploads/local"]["put"]["responses"]

    report_queue = schema["components"]["schemas"]["OperationsReportQueueItemOut"]
    assert "lifecycle_version" in report_queue["required"]
    assert report_queue["properties"]["lifecycle_version"]["minimum"] == 1
