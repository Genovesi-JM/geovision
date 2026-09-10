from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta

from app.core.time import utc_now
from app.core.tokens import create_user_access_token
from app.models import (
    Account,
    Asset,
    Company,
    CompanyUser,
    Document,
    Invitation,
    Report,
    User,
)


def _user(db_session, prefix: str, *, email: str | None = None) -> User:
    user = User(
        email=email or f"{prefix}-{uuid.uuid4().hex}@example.com",
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
                "name": f"{name} Operations",
                "customer_type": "business",
                "sector_focus": "environment",
            },
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["id"], body["workspaces"][0]["id"]


def _asset(client, owner: User, workspace_id: str) -> dict:
    response = client.post(
        "/assets",
        headers=_headers(owner, workspace_id),
        json={
            "sector": "ENVIRONMENTAL",
            "asset_type": "MONITORING_SITE",
            "name": "Existing river station",
            "geometry": {"type": "Point", "coordinates": [13.2, -8.8]},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _issue(
    client,
    owner: User,
    organization_id: str,
    workspace_id: str,
    email: str,
    *,
    target_type: str = "workspace",
    target_id: str | None = None,
    role: str = "viewer",
    metadata: dict | None = None,
):
    response = client.post(
        "/invitations",
        headers=_headers(owner, workspace_id),
        json={
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "target_email": email,
            "intended_role": role,
            "target_type": target_type,
            "target_id": target_id,
            "expires_in_hours": 24,
            "metadata": metadata or {"campaign": "phase-6"},
        },
    )
    assert response.status_code == 201, response.text
    return response


def test_preprovisioned_invite_accepts_into_existing_asset_without_recreation(
    client,
    db_session,
):
    owner = _user(db_session, "invite-owner")
    recipient = _user(db_session, "invite-recipient")
    organization_id, workspace_id = _organization(client, owner, "Shared Water")
    asset = _asset(client, owner, workspace_id)
    asset_count = db_session.query(Asset).count()

    issued_response = _issue(
        client,
        owner,
        organization_id,
        workspace_id,
        recipient.email,
        target_type="asset",
        target_id=asset["id"],
    )
    issued = issued_response.json()
    token = issued["token"]
    assert issued_response.headers["cache-control"] == "no-store"
    assert token not in issued["accept_url"].split("#", 1)[0]
    assert issued["accept_url"].endswith(f"#invitation={token}")
    assert issued["destination"]["path"] == f"/assets/{asset['id']}"

    duplicate_live = client.post(
        "/invitations",
        headers=_headers(owner, workspace_id),
        json={
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "target_email": recipient.email,
            "intended_role": "admin",
        },
    )
    assert duplicate_live.status_code == 409
    assert duplicate_live.json()["detail"]["code"] == "pending_invitation_exists"

    db_session.expire_all()
    persisted = db_session.get(Invitation, issued["id"])
    assert persisted is not None
    assert persisted.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in persisted.token_hash
    pending_member = db_session.get(CompanyUser, issued["membership_id"])
    assert pending_member is not None
    assert pending_member.user_id is None
    assert pending_member.status == "invited"

    before = client.get(
        f"/assets/{asset['id']}", headers=_headers(recipient, workspace_id)
    )
    assert before.status_code == 403

    preview = client.post("/invitations/preview", json={"token": token})
    assert preview.status_code == 200, preview.text
    assert preview.headers["cache-control"] == "no-store"
    assert preview.json()["target_email_hint"] != recipient.email
    assert preview.json()["organization_name"] == "Shared Water"

    accepted = client.post(
        "/invitations/accept",
        headers=_headers(recipient),
        json={"token": token},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["accepted"] is True
    assert accepted.json()["idempotent"] is False
    assert accepted.json()["invitation"]["destination"]["target_id"] == asset["id"]

    db_session.expire_all()
    assert db_session.query(Asset).count() == asset_count
    membership = db_session.get(CompanyUser, issued["membership_id"])
    assert membership.user_id == recipient.id
    assert membership.status == "active"
    assert membership.role == "viewer"
    readable = client.get(
        f"/assets/{asset['id']}", headers=_headers(recipient, workspace_id)
    )
    assert readable.status_code == 200, readable.text

    retry = client.post(
        "/invitations/accept",
        headers=_headers(recipient),
        json={"token": token},
    )
    assert retry.status_code == 200
    assert retry.json()["idempotent"] is True

    attacker = _user(db_session, "invite-attacker")
    reused = client.post(
        "/invitations/accept",
        headers=_headers(attacker),
        json={"token": token},
    )
    assert reused.status_code == 409
    assert reused.json()["detail"]["code"] == "invitation_used"


def test_workspace_less_invitation_targets_are_quarantined_once_scope_is_ambiguous(
    client,
    db_session,
):
    owner = _user(db_session, "legacy-target-owner")
    organization_id, workspace_a = _organization(
        client,
        owner,
        "Legacy target scope",
    )
    canonical_asset = _asset(client, owner, workspace_a)
    legacy_asset = Asset(
        organization_id=organization_id,
        workspace_id=None,
        sector="ENVIRONMENTAL",
        asset_type="MONITORING_SITE",
        name="Workspace-less legacy station",
        status="active",
        metadata_json="{}",
    )
    db_session.add(legacy_asset)
    db_session.flush()

    def report_for(asset_id: str, workspace_id: str | None, label: str) -> Report:
        return Report(
            organization_id=organization_id,
            workspace_id=workspace_id,
            asset_id=asset_id,
            report_type="ENVIRONMENTAL_MONITORING",
            title=label,
            template_version="1.0.0",
            revision=1,
            status="PUBLISHED",
            published_at=utc_now(),
            qa_level="HUMAN_REVIEW",
            context_schema_version="geovision.report-context.v1",
            context_json="{}",
            context_sha256=hashlib.sha256(label.encode()).hexdigest(),
            narrative_provider="deterministic",
            narrative_schema_version="geovision.report-narrative.v1",
            narrative_json="{}",
            qa_result_json="{}",
            generation_key=f"legacy-target-{uuid.uuid4().hex}",
        )

    legacy_report = report_for(
        legacy_asset.id,
        None,
        "Workspace-less legacy report",
    )
    canonical_report = report_for(
        canonical_asset["id"],
        workspace_a,
        "Canonical workspace A report",
    )
    legacy_document = Document(
        company_id=organization_id,
        name="Workspace-less legacy document",
        document_type="report",
        status="published",
    )
    db_session.add_all([legacy_report, canonical_report, legacy_document])
    db_session.commit()

    # Compatibility is safe while there is only one possible active workspace.
    for target_type, target_id in (
        ("asset", legacy_asset.id),
        ("report", legacy_report.id),
        ("report", legacy_document.id),
    ):
        recipient = _user(db_session, f"single-workspace-{target_type}")
        issued = _issue(
            client,
            owner,
            organization_id,
            workspace_a,
            recipient.email,
            target_type=target_type,
            target_id=target_id,
        )
        assert issued.status_code == 201

    second = client.post(
        f"/organizations/{organization_id}/workspaces",
        headers=_headers(owner, workspace_a),
        json={
            "name": "Legacy target second workspace",
            "customer_type": "business",
            "sector_focus": "environment",
            "modules_enabled": ["reports"],
        },
    )
    assert second.status_code == 201, second.text
    workspace_b = second.json()["id"]

    # No selected workspace may claim a workspace-less target after the
    # organization becomes ambiguous.
    for index, (target_type, target_id) in enumerate(
        (
            ("asset", legacy_asset.id),
            ("report", legacy_report.id),
            ("report", legacy_document.id),
        )
    ):
        recipient = _user(db_session, f"ambiguous-target-{index}")
        response = client.post(
            "/invitations",
            headers=_headers(owner, workspace_a),
            json={
                "organization_id": organization_id,
                "workspace_id": workspace_a,
                "target_email": recipient.email,
                "intended_role": "viewer",
                "target_type": target_type,
                "target_id": target_id,
            },
        )
        assert response.status_code == 404

    # Canonical targets cannot cross between two workspaces in the same tenant.
    for index, (target_type, target_id) in enumerate(
        (
            ("asset", canonical_asset["id"]),
            ("report", canonical_report.id),
        )
    ):
        recipient = _user(db_session, f"cross-workspace-target-{index}")
        response = client.post(
            "/invitations",
            headers=_headers(owner, workspace_b),
            json={
                "organization_id": organization_id,
                "workspace_id": workspace_b,
                "target_email": recipient.email,
                "intended_role": "viewer",
                "target_type": target_type,
                "target_id": target_id,
            },
        )
        assert response.status_code == 404


def test_tampered_mismatched_expired_and_revoked_tokens_fail_closed(client, db_session):
    owner = _user(db_session, "secure-owner")
    recipient = _user(db_session, "secure-recipient")
    wrong_user = _user(db_session, "wrong-recipient")
    organization_id, workspace_id = _organization(client, owner, "Secure Invite")

    issued = _issue(
        client, owner, organization_id, workspace_id, recipient.email
    ).json()
    token = issued["token"]
    tampered = client.post(
        "/invitations/preview", json={"token": token[:-1] + ("A" if token[-1] != "A" else "B")}
    )
    assert tampered.status_code == 404

    mismatch = client.post(
        "/invitations/accept",
        headers=_headers(wrong_user),
        json={"token": token},
    )
    assert mismatch.status_code == 403
    assert mismatch.json()["detail"]["code"] == "authenticated_email_mismatch"
    db_session.expire_all()
    assert db_session.get(Invitation, issued["id"]).status == "pending"

    db_session.get(Invitation, issued["id"]).expires_at = utc_now() - timedelta(seconds=1)
    db_session.commit()
    expired = client.post("/invitations/preview", json={"token": token})
    assert expired.status_code == 410
    assert expired.json()["detail"]["code"] == "invitation_expired"
    db_session.expire_all()
    assert db_session.get(Invitation, issued["id"]).status == "expired"

    revoked_recipient = _user(db_session, "revoked-recipient")
    revoked_issue = _issue(
        client,
        owner,
        organization_id,
        workspace_id,
        revoked_recipient.email,
    ).json()
    revoked = client.post(
        f"/invitations/{revoked_issue['id']}/revoke",
        headers=_headers(owner, workspace_id),
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    revoked_acceptance = client.post(
        "/invitations/accept",
        headers=_headers(revoked_recipient),
        json={"token": revoked_issue["token"]},
    )
    assert revoked_acceptance.status_code == 410
    assert revoked_acceptance.json()["detail"]["code"] == "invitation_revoked"


def test_inviter_permissions_target_isolation_and_role_escalation_are_guarded(
    client,
    db_session,
):
    owner_a = _user(db_session, "isolation-owner-a")
    owner_b = _user(db_session, "isolation-owner-b")
    viewer = _user(db_session, "isolation-viewer")
    recipient = _user(db_session, "isolation-recipient")
    org_a, workspace_a = _organization(client, owner_a, "Invitation Tenant A")
    org_b, workspace_b = _organization(client, owner_b, "Invitation Tenant B")
    asset_b = _asset(client, owner_b, workspace_b)

    viewer_membership = client.post(
        f"/organizations/{org_a}/members",
        headers=_headers(owner_a, workspace_a),
        json={"email": viewer.email, "user_id": viewer.id, "role": "viewer"},
    )
    assert viewer_membership.status_code == 201
    denied = client.post(
        "/invitations",
        headers=_headers(viewer, workspace_a),
        json={
            "organization_id": org_a,
            "workspace_id": workspace_a,
            "target_email": recipient.email,
            "intended_role": "member",
        },
    )
    assert denied.status_code == 404

    cross_tenant = client.post(
        "/invitations",
        headers=_headers(owner_a, workspace_a),
        json={
            "organization_id": org_a,
            "workspace_id": workspace_a,
            "target_email": recipient.email,
            "intended_role": "member",
            "target_type": "asset",
            "target_id": asset_b["id"],
        },
    )
    assert cross_tenant.status_code == 404

    owner_role = client.post(
        "/invitations",
        headers=_headers(owner_a, workspace_a),
        json={
            "organization_id": org_a,
            "workspace_id": workspace_a,
            "target_email": recipient.email,
            "intended_role": "owner",
        },
    )
    assert owner_role.status_code == 422

    secret_metadata = client.post(
        "/invitations",
        headers=_headers(owner_a, workspace_a),
        json={
            "organization_id": org_a,
            "workspace_id": workspace_a,
            "target_email": recipient.email,
            "intended_role": "member",
            "metadata": {"api_key": "must-not-be-stored"},
        },
    )
    assert secret_metadata.status_code == 400
    assert secret_metadata.json()["detail"]["code"] == "secret_metadata_rejected"

    for unsafe_key in ("accessToken", "clientSecret"):
        camel_case_secret = client.post(
            "/invitations",
            headers=_headers(owner_a, workspace_a),
            json={
                "organization_id": org_a,
                "workspace_id": workspace_a,
                "target_email": recipient.email,
                "intended_role": "member",
                "metadata": {"provider": [{unsafe_key: "must-not-be-stored"}]},
            },
        )
        assert camel_case_secret.status_code == 400
        assert camel_case_secret.json()["detail"]["code"] == (
            "secret_metadata_rejected"
        )

    tokenized_metadata = client.post(
        "/invitations",
        headers=_headers(owner_a, workspace_a),
        json={
            "organization_id": org_a,
            "workspace_id": workspace_a,
            "target_email": recipient.email,
            "intended_role": "member",
            "metadata": {"tokenized_amount": 125_000},
        },
    )
    assert tokenized_metadata.status_code == 201, tokenized_metadata.text


def test_intent_first_onboarding_contract_has_no_account_type_choice(client, db_session):
    options = client.get("/onboarding/options")
    assert options.status_code == 200
    rows = options.json()
    assert [row["id"] for row in rows] == [
        "request_service",
        "monitor_asset",
        "buy_product",
        "view_invitation",
    ]
    serialized = str(rows).lower()
    assert "customer_type" not in serialized
    assert "account_type" not in serialized

    user = _user(db_session, "intent-user")
    context = client.get("/onboarding/context", headers=_headers(user))
    assert context.status_code == 200
    assert context.json()["onboarding_complete"] is False
    assert context.json()["workspace_ids"] == []

    resolution = client.post(
        "/onboarding/intent",
        headers=_headers(user),
        json={"intent": "request_service"},
    )
    assert resolution.status_code == 200
    assert resolution.json() == {
        "intent": "request_service",
        "next_path": "/work/new",
        "onboarding_required": True,
        "invitation_preview": None,
    }


def test_invitation_registration_does_not_create_a_duplicate_starter_workspace(
    client,
    db_session,
):
    owner = _user(db_session, "registration-owner")
    organization_id, workspace_id = _organization(
        client, owner, "Pre-provisioned Registration"
    )
    invited_email = f"new-invite-{uuid.uuid4().hex}@example.com"
    issued = _issue(
        client,
        owner,
        organization_id,
        workspace_id,
        invited_email,
        role="member",
    ).json()

    company_count = db_session.query(Company).count()
    workspace_count = db_session.query(Account).count()
    registered = client.post(
        "/auth/register",
        headers={"X-GeoVision-Client": "mobile"},
        json={
            "email": invited_email,
            "password": "Invite-Only-Account-2026!",
            "full_name": "Invited Operator",
            "intent": "view_invitation",
        },
    )
    assert registered.status_code == 201, registered.text
    body = registered.json()
    assert body["account"] is None
    assert body["access_token"]
    assert body["refresh_token"]

    db_session.expire_all()
    assert db_session.query(Company).count() == company_count
    assert db_session.query(Account).count() == workspace_count

    accepted = client.post(
        "/invitations/accept",
        headers={"Authorization": f"Bearer {body['access_token']}"},
        json={"token": issued["token"]},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["invitation"]["workspace_id"] == workspace_id

    db_session.expire_all()
    assert db_session.query(Company).count() == company_count
    assert db_session.query(Account).count() == workspace_count
