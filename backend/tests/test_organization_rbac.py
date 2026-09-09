from __future__ import annotations

import uuid

from app.core.tokens import create_user_access_token
from app.models import (
    AccountMember,
    CompanyUser,
    InternalRoleAssignment,
    User,
)


def _create_user(db_session, prefix: str, *, role: str = "cliente") -> User:
    user = User(
        email=f"{prefix}-{uuid.uuid4().hex}@example.com",
        password_hash=None,
        role=role,
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


def _organization_payload(name: str) -> dict:
    return {
        "name": name,
        "organization_type": "customer",
        "country": "Angola",
        "timezone": "Africa/Luanda",
        "workspace": {
            "name": f"{name} Operations",
            "customer_type": "business",
            "sector_focus": "environment",
            "use_cases": ["site_environment"],
        },
    }


def _create_organization(client, owner: User, name: str) -> dict:
    response = client.post(
        "/organizations",
        headers=_headers(owner),
        json=_organization_payload(name),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_one_identity_can_list_and_select_multiple_workspaces(
    client,
    db_session,
):
    owner = _create_user(db_session, "multi-workspace")
    first = _create_organization(client, owner, "North Region")
    second = _create_organization(client, owner, "South Region")

    listed = client.get("/organizations", headers=_headers(owner))
    assert listed.status_code == 200
    assert {row["id"] for row in listed.json()} == {first["id"], second["id"]}
    assert all(row["role"] == "owner" for row in listed.json())
    assert all(len(row["workspaces"]) == 1 for row in listed.json())

    second_workspace = second["workspaces"][0]["id"]
    selected = client.post(
        "/organizations/context",
        headers=_headers(owner),
        json={"workspace_id": second_workspace},
    )
    assert selected.status_code == 200
    assert selected.json()["user_id"] == owner.id
    assert selected.json()["active_workspace_id"] == second_workspace
    assert selected.json()["active_organization_id"] == second["id"]
    assert selected.json()["workspace_role"] == "owner"
    assert selected.json()["organization_role"] == "owner"
    assert "organization:manage_members" in selected.json()["permissions"]

    header_selected = client.get(
        "/organizations/context",
        headers=_headers(owner, second_workspace),
    )
    assert header_selected.status_code == 200
    assert header_selected.json()["active_organization_id"] == second["id"]

    conflicting_headers = _headers(owner, second_workspace)
    conflicting_headers["X-Account-ID"] = first["workspaces"][0]["id"]
    conflict = client.get("/organizations/context", headers=conflicting_headers)
    assert conflict.status_code == 400


def test_horizontal_isolation_and_viewer_mutation_denial(client, db_session):
    owner = _create_user(db_session, "organization-owner")
    viewer = _create_user(db_session, "organization-viewer")
    outsider = _create_user(db_session, "organization-outsider")
    organization = _create_organization(client, owner, "Viewer Boundary")
    workspace_id = organization["workspaces"][0]["id"]

    added = client.post(
        f"/organizations/{organization['id']}/members",
        headers=_headers(owner, workspace_id),
        json={
            "email": viewer.email,
            "user_id": viewer.id,
            "role": "viewer",
        },
    )
    assert added.status_code == 201, added.text
    assert added.json()["status"] == "active"

    readable = client.get(
        f"/organizations/{organization['id']}",
        headers=_headers(viewer, workspace_id),
    )
    assert readable.status_code == 200
    assert readable.json()["role"] == "viewer"

    own_membership = client.get(
        f"/organizations/{organization['id']}/membership",
        headers=_headers(viewer, workspace_id),
    )
    assert own_membership.status_code == 200
    assert own_membership.json()["user_id"] == viewer.id

    viewer_workspace_create = client.post(
        f"/organizations/{organization['id']}/workspaces",
        headers=_headers(viewer, workspace_id),
        json={"name": "Forbidden", "customer_type": "business"},
    )
    assert viewer_workspace_create.status_code == 404

    viewer_member_create = client.post(
        f"/organizations/{organization['id']}/members",
        headers=_headers(viewer, workspace_id),
        json={"email": outsider.email, "user_id": outsider.id, "role": "member"},
    )
    assert viewer_member_create.status_code == 404

    outsider_read = client.get(
        f"/organizations/{organization['id']}",
        headers=_headers(outsider),
    )
    assert outsider_read.status_code == 404
    outsider_context = client.get(
        "/organizations/context",
        headers=_headers(outsider, workspace_id),
    )
    assert outsider_context.status_code == 403

    owner_members = client.get(
        f"/organizations/{organization['id']}/members",
        headers=_headers(owner, workspace_id),
    )
    assert owner_members.status_code == 200
    assert {row["user_id"] for row in owner_members.json()} == {owner.id, viewer.id}


def test_member_role_and_status_propagate_to_every_workspace(client, db_session):
    owner = _create_user(db_session, "role-owner")
    member = _create_user(db_session, "role-member")
    organization = _create_organization(client, owner, "Role Propagation")
    first_workspace = organization["workspaces"][0]["id"]

    second_workspace_response = client.post(
        f"/organizations/{organization['id']}/workspaces",
        headers=_headers(owner, first_workspace),
        json={
            "name": "Second Workspace",
            "customer_type": "construction",
            "sector_focus": "construction",
        },
    )
    assert second_workspace_response.status_code == 201, second_workspace_response.text
    second_workspace = second_workspace_response.json()["id"]

    added = client.post(
        f"/organizations/{organization['id']}/members",
        headers=_headers(owner, first_workspace),
        json={"email": member.email, "user_id": member.id, "role": "manager"},
    )
    assert added.status_code == 201, added.text
    membership_id = added.json()["id"]

    workspace_rows = (
        db_session.query(AccountMember)
        .filter(AccountMember.user_id == member.id)
        .all()
    )
    assert {row.account_id for row in workspace_rows} == {
        first_workspace,
        second_workspace,
    }
    assert {row.role for row in workspace_rows} == {"manager"}

    changed = client.patch(
        f"/organizations/{organization['id']}/members/{membership_id}",
        headers=_headers(owner, first_workspace),
        json={"role": "viewer"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["role"] == "viewer"
    db_session.expire_all()
    assert {
        row.role
        for row in db_session.query(AccountMember)
        .filter(AccountMember.user_id == member.id)
        .all()
    } == {"viewer"}

    revoked = client.delete(
        f"/organizations/{organization['id']}/members/{membership_id}",
        headers=_headers(owner, first_workspace),
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    denied = client.get(
        "/organizations/context",
        headers=_headers(member, first_workspace),
    )
    assert denied.status_code == 403


def test_invitation_state_and_last_owner_invariant(client, db_session):
    owner = _create_user(db_session, "invitation-owner")
    second_owner = _create_user(db_session, "second-owner")
    organization = _create_organization(client, owner, "Invitation Lifecycle")
    workspace_id = organization["workspaces"][0]["id"]

    pending = client.post(
        f"/organizations/{organization['id']}/members",
        headers=_headers(owner, workspace_id),
        json={"email": "future-user@example.com", "role": "member"},
    )
    assert pending.status_code == 201, pending.text
    assert pending.json()["user_id"] is None
    assert pending.json()["status"] == "invited"
    assert pending.json()["invited_by_user_id"] == owner.id

    premature_accept = client.patch(
        f"/organizations/{organization['id']}/members/{pending.json()['id']}",
        headers=_headers(owner, workspace_id),
        json={"status": "active"},
    )
    assert premature_accept.status_code == 409

    owner_membership = client.get(
        f"/organizations/{organization['id']}/membership",
        headers=_headers(owner, workspace_id),
    ).json()
    last_owner = client.patch(
        f"/organizations/{organization['id']}/members/{owner_membership['id']}",
        headers=_headers(owner, workspace_id),
        json={"role": "admin"},
    )
    assert last_owner.status_code == 409

    add_owner = client.post(
        f"/organizations/{organization['id']}/members",
        headers=_headers(owner, workspace_id),
        json={
            "email": second_owner.email,
            "user_id": second_owner.id,
            "role": "owner",
        },
    )
    assert add_owner.status_code == 201, add_owner.text
    demoted = client.patch(
        f"/organizations/{organization['id']}/members/{owner_membership['id']}",
        headers=_headers(owner, workspace_id),
        json={"role": "admin"},
    )
    assert demoted.status_code == 200
    assert demoted.json()["role"] == "admin"


def test_internal_roles_are_not_customer_membership_roles(client, db_session):
    support = _create_user(db_session, "internal-support")
    db_session.add(
        InternalRoleAssignment(user_id=support.id, role="GV_SUPPORT")
    )
    db_session.commit()

    context = client.get("/organizations/context", headers=_headers(support))
    assert context.status_code == 200
    assert context.json()["internal_roles"] == ["GV_SUPPORT"]
    assert "support:access" in context.json()["permissions"]
    assert "platform:admin" not in context.json()["permissions"]
    assert context.json()["organization_role"] is None

    owner = _create_user(db_session, "customer-role-owner")
    organization = _create_organization(client, owner, "Role Separation")
    workspace_id = organization["workspaces"][0]["id"]
    invalid_customer_role = client.post(
        f"/organizations/{organization['id']}/members",
        headers=_headers(owner, workspace_id),
        json={"email": support.email, "user_id": support.id, "role": "GV_SUPPORT"},
    )
    assert invalid_customer_role.status_code == 422
    assert (
        db_session.query(CompanyUser)
        .filter(
            CompanyUser.user_id == support.id,
            CompanyUser.company_id == organization["id"],
        )
        .count()
        == 0
    )


def test_suspended_organization_membership_overrides_stale_workspace_row(
    client,
    db_session,
):
    owner = _create_user(db_session, "suspension-owner")
    member = _create_user(db_session, "suspension-member")
    organization = _create_organization(client, owner, "Suspension Boundary")
    workspace_id = organization["workspaces"][0]["id"]
    added = client.post(
        f"/organizations/{organization['id']}/members",
        headers=_headers(owner, workspace_id),
        json={"email": member.email, "user_id": member.id, "role": "member"},
    )
    assert added.status_code == 201

    membership = db_session.get(CompanyUser, added.json()["id"])
    membership.status = "suspended"
    membership.is_active = False
    # Simulate a partial legacy update: the workspace row is deliberately left
    # active. Canonical organization suspension must still win.
    db_session.commit()

    denied = client.get(
        "/organizations/context",
        headers=_headers(member, workspace_id),
    )
    assert denied.status_code == 403


def test_legacy_account_header_remains_a_supported_alias(client, db_session):
    owner = _create_user(db_session, "account-header")
    organization = _create_organization(client, owner, "Header Compatibility")
    workspace_id = organization["workspaces"][0]["id"]
    headers = _headers(owner)
    headers["X-Account-ID"] = workspace_id
    response = client.get("/organizations/context", headers=headers)
    assert response.status_code == 200
    assert response.json()["active_workspace_id"] == workspace_id
    assert response.json()["active_organization_id"] == organization["id"]
