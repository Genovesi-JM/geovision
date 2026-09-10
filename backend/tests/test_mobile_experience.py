from __future__ import annotations

import uuid
from datetime import timedelta

from app.core.time import utc_now
from app.core.tokens import create_user_access_token
from app.models import Action, Asset, IotDevice, MobileServiceRequest, Order, Report, User


def _user(db_session, prefix: str) -> User:
    user = User(
        email=f"{prefix}-{uuid.uuid4().hex}@example.com",
        password_hash=None,
        role="cliente",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
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


def _organization(
    client,
    owner: User,
    name: str,
    *,
    modules: list[str] | None = None,
) -> tuple[str, str]:
    response = client.post(
        "/organizations",
        headers=_headers(owner),
        json={
            "name": name,
            "country": "Angola",
            "timezone": "Africa/Luanda",
            "workspace": {
                "name": f"{name} North",
                "customer_type": "business",
                "sector_focus": "agro",
                "modules_enabled": modules
                if modules is not None
                else ["projects", "alerts", "store"],
            },
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["id"], body["workspaces"][0]["id"]


def _add_workspace(
    client,
    owner: User,
    organization_id: str,
    first_workspace_id: str,
    *,
    name: str,
    modules: list[str],
) -> str:
    response = client.post(
        f"/organizations/{organization_id}/workspaces",
        headers=_headers(owner, first_workspace_id),
        json={
            "name": name,
            "customer_type": "business",
            "sector_focus": "infrastructure",
            "modules_enabled": modules,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _asset(client, owner: User, workspace_id: str, name: str) -> dict:
    response = client.post(
        "/assets",
        headers=_headers(owner, workspace_id),
        json={
            "sector": "AGRICULTURE",
            "asset_type": "SITE",
            "name": name,
            "geometry": {"type": "Point", "coordinates": [13.2, -8.8]},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _site(client, owner: User, workspace_id: str, name: str) -> dict:
    response = client.post(
        "/mobile/sites",
        headers=_headers(owner, workspace_id),
        json={
            "name": name,
            "sector": "agro",
            "country": "Angola",
            "province": "Huambo",
            "municipality": "Caála",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _service_request(
    client,
    owner: User,
    workspace_id: str,
    site: dict,
    description: str,
) -> dict:
    response = client.post(
        "/mobile/service-requests",
        headers=_headers(owner, workspace_id),
        json={
            "site_id": site["id"],
            "site_name": "ignored client value",
            "type": "inspection",
            "urgency": "high",
            "description": description,
            "attachments": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _action(
    db_session,
    *,
    organization_id: str,
    workspace_id: str,
    asset_id: str,
    suffix: str,
    priority: str,
    status: str,
    due_date=None,
    completed_at=None,
) -> Action:
    row = Action(
        organization_id=organization_id,
        workspace_id=workspace_id,
        asset_id=asset_id,
        source_rule_key=f"phase22.{suffix}",
        source_rule_version="1.0.0",
        priority=priority,
        title=f"Action {suffix}",
        description=f"Customer action {suffix}",
        status=status,
        due_date=due_date,
        recommendation_refs_json="[]",
        outcome_json="{}",
        deduplication_key=f"phase22-{suffix}-{uuid.uuid4().hex}",
        completed_at=completed_at,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_mobile_experience_honors_workspace_modules_permissions_and_memberships(
    client,
    db_session,
):
    owner = _user(db_session, "mobile-experience-owner")
    organization_id, workspace_a = _organization(
        client,
        owner,
        "Mobile Experience",
        modules=["projects", "alerts", "store"],
    )
    workspace_b = _add_workspace(
        client,
        owner,
        organization_id,
        workspace_a,
        name="Mobile Experience South",
        modules=["projects", "reports", "iot"],
    )

    first = client.get("/mobile/experience", headers=_headers(owner, workspace_a))
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["active_workspace_id"] == workspace_a
    assert body["active_organization_id"] == organization_id
    assert {row["id"] for row in body["workspaces"]} == {workspace_a, workspace_b}
    assert body["workspaces"][0]["organization_name"] == "Mobile Experience"
    assert "reports" not in body["capabilities"]
    assert "devices" not in body["capabilities"]
    assert {"assets", "actions", "services", "team", "billing", "settings", "support"}.issubset(
        body["capabilities"]
    )

    contextual_site = _site(client, owner, workspace_a, "Connected North Site")
    contextual_asset = (
        db_session.query(Asset)
        .filter(
            Asset.legacy_source == "site",
            Asset.legacy_source_id == contextual_site["id"],
        )
        .one()
    )
    device = IotDevice(
            public_id=f"gv-phase22-{uuid.uuid4().hex}",
            company_id=organization_id,
            site_id=contextual_site["id"],
            core_asset_id=contextual_asset.id,
            name="Workspace gateway",
            token_hash="phase22-token-hash",
            secret_encrypted="phase22-encrypted-secret",
        )
    db_session.add(
        device
    )
    db_session.commit()
    contextual = client.get(
        "/mobile/experience",
        headers=_headers(owner, workspace_a),
    )
    assert "devices" in contextual.json()["capabilities"]
    assert "reports" not in contextual.json()["capabilities"]
    devices_a = client.get("/mobile/devices", headers=_headers(owner, workspace_a))
    devices_b = client.get("/mobile/devices", headers=_headers(owner, workspace_b))
    assert {row["id"] for row in devices_a.json()["items"]} == {device.id}
    assert devices_b.json()["items"] == []

    second = client.get("/mobile/experience", headers=_headers(owner, workspace_b))
    assert second.status_code == 200, second.text
    assert {"reports", "devices"}.issubset(second.json()["capabilities"])
    assert second.json()["active_workspace_id"] == workspace_b

    viewer = _user(db_session, "mobile-experience-viewer")
    added = client.post(
        f"/organizations/{organization_id}/members",
        headers=_headers(owner, workspace_a),
        json={"email": viewer.email, "user_id": viewer.id, "role": "viewer"},
    )
    assert added.status_code == 201, added.text
    viewer_experience = client.get(
        "/mobile/experience",
        headers=_headers(viewer, workspace_a),
    )
    assert viewer_experience.status_code == 200, viewer_experience.text
    assert "team" not in viewer_experience.json()["capabilities"]
    assert "billing" not in viewer_experience.json()["capabilities"]
    assert {"settings", "support"}.issubset(
        viewer_experience.json()["capabilities"]
    )

    outsider = _user(db_session, "mobile-experience-outsider")
    _, outsider_workspace = _organization(client, outsider, "Other Mobile Tenant")
    denied = client.get(
        "/mobile/experience",
        headers=_headers(owner, outsider_workspace),
    )
    assert denied.status_code == 403


def test_mobile_home_and_actions_are_attention_focused_and_asset_scoped(
    client,
    db_session,
):
    owner = _user(db_session, "mobile-home-owner")
    organization_id, workspace_id = _organization(client, owner, "Mobile Home")
    asset = _asset(client, owner, workspace_id, "Attention Farm")
    other_asset = _asset(client, owner, workspace_id, "Quiet Farm")
    now = utc_now()
    critical = _action(
        db_session,
        organization_id=organization_id,
        workspace_id=workspace_id,
        asset_id=asset["id"],
        suffix="critical",
        priority="URGENT",
        status="OPEN",
        due_date=now + timedelta(hours=2),
    )
    attention = _action(
        db_session,
        organization_id=organization_id,
        workspace_id=workspace_id,
        asset_id=asset["id"],
        suffix="attention",
        priority="HIGH",
        status="IN_PROGRESS",
        due_date=now - timedelta(hours=1),
    )
    scheduled = _action(
        db_session,
        organization_id=organization_id,
        workspace_id=workspace_id,
        asset_id=asset["id"],
        suffix="scheduled",
        priority="MEDIUM",
        status="OPEN",
        due_date=now + timedelta(days=3),
    )
    completed = _action(
        db_session,
        organization_id=organization_id,
        workspace_id=workspace_id,
        asset_id=asset["id"],
        suffix="completed",
        priority="LOW",
        status="COMPLETED",
        completed_at=now - timedelta(days=1),
    )
    dismissed = _action(
        db_session,
        organization_id=organization_id,
        workspace_id=workspace_id,
        asset_id=asset["id"],
        suffix="dismissed",
        priority="HIGH",
        status="DISMISSED",
    )
    other = _action(
        db_session,
        organization_id=organization_id,
        workspace_id=workspace_id,
        asset_id=other_asset["id"],
        suffix="other-asset",
        priority="HIGH",
        status="OPEN",
    )

    site = _site(client, owner, workspace_id, "Service Farm")
    active_request = _service_request(
        client,
        owner,
        workspace_id,
        site,
        "Inspect irrigation equipment.",
    )
    completed_request = _service_request(
        client,
        owner,
        workspace_id,
        site,
        "Published field inspection result.",
    )
    completed_row = db_session.get(MobileServiceRequest, completed_request["id"])
    completed_row.status = "completed"
    completed_row.updated_at = now
    db_session.commit()

    actions = client.get("/mobile/actions", headers=_headers(owner, workspace_id))
    assert actions.status_code == 200, actions.text
    grouped = actions.json()
    assert critical.id in {row["id"] for row in grouped["critical"]}
    assert attention.id in {row["id"] for row in grouped["attention"]}
    assert scheduled.id in {row["id"] for row in grouped["scheduled"]}
    assert completed.id in {row["id"] for row in grouped["completed"]}
    assert dismissed.id not in {
        row["id"] for bucket in grouped.values() for row in bucket
    }

    contextual = client.get(
        f"/mobile/actions?asset_id={asset['id']}",
        headers=_headers(owner, workspace_id),
    )
    assert contextual.status_code == 200, contextual.text
    contextual_ids = {
        row["id"]
        for bucket in contextual.json().values()
        for row in bucket
    }
    assert other.id not in contextual_ids
    assert contextual_ids == {critical.id, attention.id, scheduled.id, completed.id}

    home = client.get("/mobile/home", headers=_headers(owner, workspace_id))
    assert home.status_code == 200, home.text
    summary = home.json()
    assert summary["workspace_id"] == workspace_id
    assert summary["attention"] == {
        "critical": 1,
        "attention": 2,
        "scheduled": 1,
        "completed_recent": 1,
        "active_services": 1,
        "offline_devices": 0,
    }
    assert summary["priority_items"][0]["id"] == critical.id
    assert summary["priority_items"][0]["target_type"] == "ACTION"
    assert summary["latest_result"]["target_type"] == "SERVICE_RESULT"
    assert summary["latest_result"]["target_id"] == completed_request["id"]
    assert active_request["id"] != completed_request["id"]


def test_mobile_sites_services_and_service_deep_link_are_workspace_isolated(
    client,
    db_session,
):
    owner = _user(db_session, "mobile-services-owner")
    organization_id, workspace_a = _organization(client, owner, "Mobile Services")
    workspace_b = _add_workspace(
        client,
        owner,
        organization_id,
        workspace_a,
        name="Mobile Services South",
        modules=["projects", "alerts", "store"],
    )
    site_a = _site(client, owner, workspace_a, "North Site")
    site_b = _site(client, owner, workspace_b, "South Site")
    request_a = _service_request(
        client, owner, workspace_a, site_a, "North workspace request."
    )
    request_b = _service_request(
        client, owner, workspace_b, site_b, "South workspace result."
    )
    asset_b = (
        db_session.query(Asset)
        .filter(
            Asset.legacy_source == "site",
            Asset.legacy_source_id == site_b["id"],
        )
        .one()
    )
    report = Report(
        organization_id=organization_id,
        workspace_id=workspace_b,
        asset_id=asset_b.id,
        report_type="FIELD_INSPECTION",
        title="South Site Field Inspection",
        template_version="1.0.0",
        revision=1,
        status="APPROVED",
        qa_level="HUMAN_REVIEW",
        context_schema_version="geovision.report-context.v1",
        context_json="{}",
        context_sha256="a" * 64,
        narrative_provider="deterministic",
        narrative_schema_version="geovision.report-narrative.v1",
        narrative_json="{}",
        qa_result_json="{}",
        generation_key=f"phase22-{uuid.uuid4().hex}",
    )
    db_session.add(report)
    db_session.commit()
    db_session.refresh(report)
    unpublished = client.get(
        f"/mobile/service-requests/{request_b['id']}",
        headers=_headers(owner, workspace_b),
    )
    assert unpublished.status_code == 200, unpublished.text
    assert unpublished.json()["result"] is None
    report.status = "PUBLISHED"
    report.published_at = utc_now()
    db_session.commit()

    sites_a = client.get("/mobile/sites", headers=_headers(owner, workspace_a))
    sites_b = client.get("/mobile/sites", headers=_headers(owner, workspace_b))
    assert {row["id"] for row in sites_a.json()} == {site_a["id"]}
    assert {row["id"] for row in sites_b.json()} == {site_b["id"]}
    services_a = client.get(
        "/mobile/service-requests", headers=_headers(owner, workspace_a)
    )
    services_b = client.get(
        "/mobile/service-requests", headers=_headers(owner, workspace_b)
    )
    assert {row["id"] for row in services_a.json()} == {request_a["id"]}
    assert {row["id"] for row in services_b.json()} == {request_b["id"]}
    wrong_asset_context = client.get(
        f"/mobile/actions?asset_id={asset_b.id}",
        headers=_headers(owner, workspace_a),
    )
    assert wrong_asset_context.status_code == 404
    assert (
        client.get(
            f"/mobile/service-requests/{request_b['id']}",
            headers=_headers(owner, workspace_a),
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/mobile/service-requests",
            headers=_headers(owner, workspace_a),
            json={
                "site_id": site_b["id"],
                "site_name": "ignored",
                "type": "inspection",
                "urgency": "normal",
                "description": "Must stay in the selected workspace.",
                "attachments": [],
            },
        ).status_code
        == 404
    )

    recipient = _user(db_session, "mobile-services-recipient")
    invalid_invitation = client.post(
        "/invitations",
        headers=_headers(owner, workspace_a),
        json={
            "organization_id": organization_id,
            "workspace_id": workspace_a,
            "target_email": recipient.email,
            "intended_role": "viewer",
            "target_type": "service_result",
            "target_id": request_b["id"],
        },
    )
    assert invalid_invitation.status_code == 404

    invitation = client.post(
        "/invitations",
        headers=_headers(owner, workspace_b),
        json={
            "organization_id": organization_id,
            "workspace_id": workspace_b,
            "target_email": recipient.email,
            "intended_role": "viewer",
            "target_type": "service_result",
            "target_id": request_b["id"],
        },
    )
    assert invitation.status_code == 201, invitation.text
    assert invitation.json()["destination"]["path"] == f"/work/{request_b['id']}"
    accepted = client.post(
        "/invitations/accept",
        headers=_headers(recipient),
        json={"token": invitation.json()["token"]},
    )
    assert accepted.status_code == 200, accepted.text
    landed = client.get(
        f"/mobile/service-requests/{request_b['id']}",
        headers=_headers(recipient, workspace_b),
    )
    assert landed.status_code == 200, landed.text
    assert landed.json()["id"] == request_b["id"]
    # Sharing an asset does not prove that a report was produced by this
    # request.  Without a durable request-to-report link, fail closed even
    # when an otherwise visible published report exists on the same asset.
    assert landed.json()["result"] is None

    outsider = _user(db_session, "mobile-services-outsider")
    _, outsider_workspace = _organization(client, outsider, "Unrelated Services Tenant")
    denied = client.get(
        f"/mobile/service-requests/{request_b['id']}",
        headers=_headers(outsider, outsider_workspace),
    )
    assert denied.status_code == 404

    db_session.expire_all()
    assert db_session.query(Asset).filter(Asset.legacy_source == "site").count() >= 2


def _canonical_order(
    db_session,
    *,
    owner: User,
    organization_id: str | None,
    workspace_id: str | None,
    suffix: str,
) -> Order:
    row = Order(
        user_id=owner.id,
        company_id=organization_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        order_number=f"GV-P22-{suffix}-{uuid.uuid4().hex[:8].upper()}",
        order_type="SERVICE",
        status="confirmed",
        fulfilment_status="CONFIRMED",
        payment_status="PENDING",
        currency="AOA",
        subtotal=1000,
        total=1000,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_canonical_customer_orders_follow_selected_workspace_and_legacy_ambiguity(
    client,
    db_session,
):
    owner = _user(db_session, "mobile-orders-owner")
    organization_id, workspace_a = _organization(client, owner, "Mobile Orders")
    workspace_b = _add_workspace(
        client,
        owner,
        organization_id,
        workspace_a,
        name="Mobile Orders South",
        modules=["projects", "alerts", "store"],
    )
    order_a = _canonical_order(
        db_session,
        owner=owner,
        organization_id=organization_id,
        workspace_id=workspace_a,
        suffix="NORTH",
    )
    order_b = _canonical_order(
        db_session,
        owner=owner,
        organization_id=organization_id,
        workspace_id=workspace_b,
        suffix="SOUTH",
    )
    ambiguous_legacy = _canonical_order(
        db_session,
        owner=owner,
        organization_id=organization_id,
        workspace_id=None,
        suffix="LEGACY",
    )

    north = client.get("/orders", headers=_headers(owner, workspace_a))
    south = client.get("/orders", headers=_headers(owner, workspace_b))
    assert north.status_code == 200, north.text
    assert south.status_code == 200, south.text
    assert {row["id"] for row in north.json()} == {order_a.id}
    assert {row["id"] for row in south.json()} == {order_b.id}
    assert ambiguous_legacy.id not in {row["id"] for row in north.json()}
    assert (
        client.get(
            f"/orders/{order_b.id}",
            headers=_headers(owner, workspace_a),
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/orders/{order_b.id}/progress",
            headers=_headers(owner, workspace_a),
        ).status_code
        == 404
    )
    denied_cancel = client.post(
        f"/orders/{order_b.id}/cancel",
        headers=_headers(owner, workspace_a),
    )
    assert denied_cancel.status_code == 404
    db_session.refresh(order_b)
    assert order_b.fulfilment_status == "CONFIRMED"

    single_owner = _user(db_session, "mobile-orders-single-owner")
    single_organization, single_workspace = _organization(
        client,
        single_owner,
        "Single Workspace Orders",
    )
    unambiguous_legacy = _canonical_order(
        db_session,
        owner=single_owner,
        organization_id=single_organization,
        workspace_id=None,
        suffix="SOLE",
    )
    visible = client.get(
        "/orders",
        headers=_headers(single_owner, single_workspace),
    )
    assert visible.status_code == 200, visible.text
    assert {row["id"] for row in visible.json()} == {unambiguous_legacy.id}
    assert (
        client.get(
            f"/orders/{unambiguous_legacy.id}",
            headers=_headers(single_owner, single_workspace),
        ).status_code
        == 200
    )

    _add_workspace(
        client,
        single_owner,
        single_organization,
        single_workspace,
        name="Second Workspace Makes Legacy Ambiguous",
        modules=["projects", "alerts", "store"],
    )
    hidden_after_split = client.get(
        "/orders",
        headers=_headers(single_owner, single_workspace),
    )
    assert hidden_after_split.status_code == 200, hidden_after_split.text
    assert unambiguous_legacy.id not in {
        row["id"] for row in hidden_after_split.json()
    }
