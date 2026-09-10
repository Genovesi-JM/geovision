from __future__ import annotations

from datetime import timedelta
import json
import uuid

from app.core.time import utc_now
from app.core.tokens import create_user_access_token
from app.models import (
    AuditLog,
    Company,
    CompanyEntitlement,
    IntegrationConnection,
    IntegrationSyncEvent,
    IntegrationSyncRun,
    User,
)


def _user(db_session, prefix: str) -> User:
    row = User(
        email=f"{prefix}-{uuid.uuid4().hex}@example.com",
        password_hash=None,
        role="cliente",
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
    headers = {"Authorization": f"Bearer {token}"}
    if workspace_id:
        headers["X-Workspace-ID"] = workspace_id
    return headers


def _organization(client, db_session, owner: User, name: str) -> tuple[str, str]:
    response = client.post(
        "/organizations",
        headers=_headers(owner),
        json={
            "name": name,
            "country": "Angola",
            "timezone": "Africa/Luanda",
            "workspace": {
                "name": f"{name} Workspace",
                "customer_type": "construction",
                "sector_focus": "construction",
            },
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    organization = db_session.get(Company, body["id"])
    organization.subscription_plan = "enterprise"
    db_session.commit()
    return body["id"], body["workspaces"][0]["id"]


def _connection_payload(workspace_id: str, **overrides) -> dict:
    payload = {
        "workspace_id": workspace_id,
        "connection_key": f"fixture_{uuid.uuid4().hex[:12]}",
        "provider_family": "construction",
        "provider_code": "fake",
        "display_name": "Construction contract fixture",
        "credential_reference": (
            "https://geovision-test.vault.azure.net/secrets/construction/token-v1"
        ),
        "settings": {"region": "africa-south", "project_mapping": "stable"},
        "capabilities": ["project.read", "project.write", "inspection.read"],
        "timeout_seconds": 15,
        "retry_max_attempts": 3,
        "retry_base_seconds": 1,
        "rate_limit_per_minute": 10,
        "circuit_failure_threshold": 2,
    }
    payload.update(overrides)
    return payload


def _create_connection(client, headers: dict[str, str], workspace_id: str, **overrides):
    response = client.post(
        "/integration-connections",
        headers=headers,
        json=_connection_payload(workspace_id, **overrides),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _flag_key(connection: dict) -> str:
    return (
        f"geovision.integrations.{connection['provider_family']}."
        f"{connection['provider_code']}"
    )


def _put_flag(
    client,
    headers: dict[str, str],
    workspace_id: str,
    connection: dict,
    *,
    enabled: bool = True,
    member_user_id: str | None = None,
    expected_version: int | None = None,
):
    payload = {
        "workspace_id": workspace_id,
        "member_user_id": member_user_id,
        "enabled": enabled,
        "source": "admin",
    }
    if expected_version is not None:
        payload["expected_version"] = expected_version
    response = client.put(
        f"/integration-connections/feature-flags/{_flag_key(connection)}",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _enable(client, headers: dict[str, str], connection: dict) -> dict:
    response = client.post(
        f"/integration-connections/{connection['id']}/enable",
        headers=headers,
        json={"expected_version": connection["version"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_connection_flag_health_sync_and_idempotency_lifecycle(client, db_session):
    owner = _user(db_session, "registry-owner")
    organization_id, workspace_id = _organization(
        client, db_session, owner, "Registry Flow"
    )
    headers = _headers(owner, workspace_id)
    connection = _create_connection(client, headers, workspace_id)

    assert connection["organization_id"] == organization_id
    assert connection["member_user_id"] is None
    assert connection["status"] == "pending_configuration"
    assert connection["credential_configured"] is True
    serialized = json.dumps(connection).lower()
    assert "vault.azure.net" not in serialized
    assert "credential_reference" not in connection
    assert "settings" not in connection

    disabled_sync = client.post(
        f"/integration-connections/{connection['id']}/sync-runs",
        headers=headers,
        json={
            "direction": "outbound",
            "operation": "synchronize_project",
            "idempotency_key": "disabled-sync-001",
            "payload": {},
        },
    )
    assert disabled_sync.status_code == 409
    assert disabled_sync.json()["detail"]["code"] == "connection_disabled"

    flag = _put_flag(client, headers, workspace_id, connection)
    assert flag["enabled"] is True
    assert flag["member_user_id"] is None
    resolved = client.get(
        f"/integration-connections/feature-flags/resolve/{_flag_key(connection)}",
        headers=headers,
        params={"workspace_id": workspace_id},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["enabled"] is True
    assert resolved.json()["scope"] == "workspace"

    connection = _enable(client, headers, connection)
    assert connection["status"] == "active"
    health = client.post(
        f"/integration-connections/{connection['id']}/health",
        headers=headers,
    )
    assert health.status_code == 200, health.text
    assert health.json()["provider_available"] is True
    assert health.json()["health_status"] == "healthy"

    sync_payload = {
        "direction": "outbound",
        "operation": "synchronize_project",
        "idempotency_key": "project-sync-001",
        "payload": {
            "resource_type": "construction_project",
            "resource_id": str(uuid.uuid4()),
            "revision": 7,
        },
        "simulation_outcome": "success",
    }
    created = client.post(
        f"/integration-connections/{connection['id']}/sync-runs",
        headers=headers,
        json=sync_payload,
    )
    assert created.status_code == 201, created.text
    run = created.json()
    assert run["status"] == "succeeded"
    assert run["attempt_count"] == 1
    assert len(run["payload_sha256"]) == 64

    duplicate = client.post(
        f"/integration-connections/{connection['id']}/sync-runs",
        headers=headers,
        json=sync_payload,
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == run["id"]
    conflict_payload = {**sync_payload, "payload": {"revision": 8}}
    conflict = client.post(
        f"/integration-connections/{connection['id']}/sync-runs",
        headers=headers,
        json=conflict_payload,
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "sync_idempotency_conflict"

    events = client.get(
        f"/integration-connections/{connection['id']}/sync-events",
        headers=headers,
        params={"run_id": run["id"]},
    )
    assert events.status_code == 200
    assert len(events.json()) == 1
    assert events.json()[0]["status"] == "succeeded"
    assert "://" not in events.json()[0]["external_reference"]

    rate_limited = client.post(
        f"/integration-connections/{connection['id']}/sync-runs",
        headers=headers,
        json={
            "direction": "inbound",
            "operation": "synchronize_project",
            "idempotency_key": "rate-limited-sync-001",
            "payload": {},
            "simulation_outcome": "rate_limited",
            "retry_after_seconds": 30,
        },
    )
    assert rate_limited.status_code == 201, rate_limited.text
    assert rate_limited.json()["status"] == "retry_scheduled"
    throttled = client.post(
        f"/integration-connections/{connection['id']}/sync-runs",
        headers=headers,
        json={
            "direction": "inbound",
            "operation": "synchronize_project",
            "idempotency_key": "rate-limit-gate-sync-001",
        },
    )
    assert throttled.status_code == 429
    assert throttled.json()["detail"]["code"] == "integration_rate_limited"
    db_session.expire_all()
    assert (
        db_session.get(IntegrationConnection, connection["id"]).circuit_breaker_state
        == "CLOSED"
    )

    audit_text = "\n".join(
        row.details
        for row in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == organization_id)
        .all()
    ).lower()
    assert "vault.azure.net" not in audit_text
    assert "token-v1" not in audit_text


def test_retry_circuit_half_open_recovery_and_disconnect_retains_history(
    client, db_session
):
    owner = _user(db_session, "resilience-owner")
    _, workspace_id = _organization(client, db_session, owner, "Resilience Flow")
    headers = _headers(owner, workspace_id)
    connection = _create_connection(
        client,
        headers,
        workspace_id,
        retry_max_attempts=2,
        circuit_failure_threshold=1,
    )
    _put_flag(client, headers, workspace_id, connection)
    connection = _enable(client, headers, connection)

    failed = client.post(
        f"/integration-connections/{connection['id']}/sync-runs",
        headers=headers,
        json={
            "direction": "inbound",
            "operation": "synchronize_project",
            "idempotency_key": "retry-sync-001",
            "payload": {},
            "simulation_outcome": "timeout",
        },
    )
    assert failed.status_code == 201, failed.text
    run = failed.json()
    assert run["status"] == "retry_scheduled"
    assert run["failure_code"] == "timeout"

    row = db_session.get(IntegrationConnection, connection["id"])
    stored_run = db_session.get(IntegrationSyncRun, run["id"])
    assert row.circuit_breaker_state == "OPEN"
    assert row.circuit_breaker_failure_count == 1
    row.circuit_breaker_state = "HALF_OPEN"
    db_session.commit()
    blocked_probe = client.post(
        f"/integration-connections/{connection['id']}/sync-runs",
        headers=headers,
        json={
            "direction": "inbound",
            "operation": "synchronize_project",
            "idempotency_key": "parallel-half-open-probe-001",
            "simulation_outcome": "success",
        },
    )
    assert blocked_probe.status_code == 503
    assert blocked_probe.json()["detail"]["code"] == "integration_circuit_half_open"
    db_session.refresh(row)
    row.circuit_breaker_state = "OPEN"
    row.circuit_breaker_opened_at = utc_now() - timedelta(minutes=2)
    stored_run.next_retry_at = utc_now() - timedelta(seconds=1)
    db_session.commit()

    recovered = client.post(
        f"/integration-connections/{connection['id']}/sync-runs/{run['id']}/retry",
        headers=headers,
        json={
            "expected_version": run["version"],
            "simulation_outcome": "success",
        },
    )
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["status"] == "succeeded"
    assert recovered.json()["attempt_count"] == 2
    db_session.expire_all()
    row = db_session.get(IntegrationConnection, connection["id"])
    assert row.circuit_breaker_state == "CLOSED"
    assert row.circuit_breaker_failure_count == 0

    latest = client.get(
        f"/integration-connections/{connection['id']}", headers=headers
    ).json()
    disconnected = client.post(
        f"/integration-connections/{connection['id']}/disconnect",
        headers=headers,
        json={
            "expected_version": latest["version"],
            "reason": "rotation token=token-v1",
        },
    )
    assert disconnected.status_code == 200, disconnected.text
    assert disconnected.json()["status"] == "disconnected"
    assert disconnected.json()["enabled"] is False
    assert disconnected.json()["credential_configured"] is False

    hidden = client.get("/integration-connections", headers=headers)
    assert hidden.status_code == 200
    assert hidden.json() == []
    retained = client.get(
        "/integration-connections",
        headers=headers,
        params={"include_disconnected": True},
    )
    assert [item["id"] for item in retained.json()] == [connection["id"]]
    retained_runs = client.get(
        f"/integration-connections/{connection['id']}/sync-runs",
        headers=headers,
    )
    assert retained_runs.status_code == 200
    assert retained_runs.json()[0]["status"] == "succeeded"
    assert (
        db_session.query(IntegrationSyncRun)
        .filter_by(connection_id=connection["id"])
        .count()
        == 1
    )
    assert (
        db_session.query(IntegrationSyncEvent)
        .filter_by(connection_id=connection["id"])
        .count()
        == 1
    )
    audit_text = "\n".join(
        row.details
        for row in db_session.query(AuditLog)
        .filter(AuditLog.resource_id == connection["id"])
        .all()
    )
    assert "token-v1" not in audit_text


def test_feature_member_precedence_tenant_isolation_and_viewer_denial(
    client, db_session
):
    owner = _user(db_session, "flag-owner")
    viewer = _user(db_session, "flag-viewer")
    outsider = _user(db_session, "flag-outsider")
    organization_id, workspace_id = _organization(
        client, db_session, owner, "Flag Boundaries"
    )
    headers = _headers(owner, workspace_id)
    added = client.post(
        f"/organizations/{organization_id}/members",
        headers=headers,
        json={"email": viewer.email, "user_id": viewer.id, "role": "viewer"},
    )
    assert added.status_code == 201, added.text
    connection = _create_connection(client, headers, workspace_id)
    member_connection = _create_connection(
        client,
        headers,
        workspace_id,
        member_user_id=viewer.id,
    )
    assert member_connection["member_user_id"] == viewer.id
    workspace_flag = _put_flag(client, headers, workspace_id, connection)
    member_flag = _put_flag(
        client,
        headers,
        workspace_id,
        connection,
        enabled=False,
        member_user_id=viewer.id,
    )
    assert workspace_flag["enabled"] is True
    assert member_flag["enabled"] is False

    viewer_resolution = client.get(
        f"/integration-connections/feature-flags/resolve/{_flag_key(connection)}",
        headers=_headers(viewer, workspace_id),
        params={"workspace_id": workspace_id},
    )
    assert viewer_resolution.status_code == 200
    assert viewer_resolution.json()["enabled"] is False
    assert viewer_resolution.json()["scope"] == "member"
    viewer_create = client.post(
        "/integration-connections",
        headers=_headers(viewer, workspace_id),
        json=_connection_payload(workspace_id),
    )
    assert viewer_create.status_code == 404

    _, outsider_workspace_id = _organization(
        client, db_session, outsider, "Other Tenant"
    )
    outsider_headers = _headers(outsider, outsider_workspace_id)
    denied = client.get(
        f"/integration-connections/{connection['id']}", headers=outsider_headers
    )
    assert denied.status_code == 404
    denied_flag = client.get(
        f"/integration-connections/feature-flags/resolve/{_flag_key(connection)}",
        headers=outsider_headers,
        params={"workspace_id": workspace_id},
    )
    assert denied_flag.status_code == 404


def test_sync_requires_entitlement_registered_operation_and_capability(
    client,
    db_session,
):
    owner = _user(db_session, "registry-entitlement-owner")
    organization_id, workspace_id = _organization(
        client,
        db_session,
        owner,
        "Registry Entitlement",
    )
    headers = _headers(owner, workspace_id)
    connection = _create_connection(
        client,
        headers,
        workspace_id,
        capabilities=["project.read"],
    )
    _put_flag(client, headers, workspace_id, connection)
    connection = _enable(client, headers, connection)

    organization = db_session.get(Company, organization_id)
    organization.subscription_plan = "trial"
    db_session.commit()
    resolution = client.get(
        f"/integration-connections/feature-flags/resolve/{_flag_key(connection)}",
        headers=headers,
        params={"workspace_id": workspace_id},
    )
    assert resolution.status_code == 200
    assert resolution.json()["enabled"] is False
    assert resolution.json()["source"] == "access_gate"
    not_entitled = client.post(
        f"/integration-connections/{connection['id']}/sync-runs",
        headers=headers,
        json={
            "direction": "inbound",
            "operation": "synchronize_project",
            "idempotency_key": "not-entitled-sync-001",
        },
    )
    assert not_entitled.status_code == 409
    assert not_entitled.json()["detail"]["code"] == "integration_feature_disabled"

    organization.subscription_plan = "enterprise"
    db_session.commit()
    unsupported = client.post(
        f"/integration-connections/{connection['id']}/sync-runs",
        headers=headers,
        json={
            "direction": "inbound",
            "operation": "arbitrary_vendor_call",
            "idempotency_key": "unsupported-sync-001",
        },
    )
    assert unsupported.status_code == 422
    assert unsupported.json()["detail"]["code"] == "sync_operation_not_supported"
    missing_capability = client.post(
        f"/integration-connections/{connection['id']}/sync-runs",
        headers=headers,
        json={
            "direction": "outbound",
            "operation": "synchronize_project",
            "idempotency_key": "missing-capability-sync-001",
        },
    )
    assert missing_capability.status_code == 403
    assert (
        missing_capability.json()["detail"]["code"] == "integration_capability_missing"
    )
    allowed = client.post(
        f"/integration-connections/{connection['id']}/sync-runs",
        headers=headers,
        json={
            "direction": "inbound",
            "operation": "synchronize_project",
            "idempotency_key": "allowed-capability-sync-001",
        },
    )
    assert allowed.status_code == 201, allowed.text
    assert allowed.json()["status"] == "succeeded"

    db_session.add(
        CompanyEntitlement(
            company_id=organization_id,
            tier="enterprise",
            sensor_allowance=25,
            valid_until=utc_now() - timedelta(days=1),
        )
    )
    db_session.commit()
    expired = client.get(
        f"/integration-connections/feature-flags/resolve/{_flag_key(connection)}",
        headers=headers,
        params={"workspace_id": workspace_id},
    )
    assert expired.status_code == 200
    assert expired.json()["enabled"] is False
    assert expired.json()["source"] == "access_gate"


def test_registry_rejects_raw_secrets_and_unapproved_live_provider(client, db_session):
    owner = _user(db_session, "secure-registry-owner")
    _, workspace_id = _organization(client, db_session, owner, "Secure Registry")
    headers = _headers(owner, workspace_id)

    raw_secret = client.post(
        "/integration-connections",
        headers=headers,
        json=_connection_payload(
            workspace_id,
            settings={"nested": {"api_key": "do-not-echo-settings-secret"}},
        ),
    )
    assert raw_secret.status_code == 422
    assert "do-not-echo-settings-secret" not in raw_secret.text
    bad_endpoint = client.post(
        "/integration-connections",
        headers=headers,
        json=_connection_payload(
            workspace_id,
            endpoint_url="https://user:do-not-echo-endpoint-secret@example.com/api",
        ),
    )
    assert bad_endpoint.status_code == 422
    assert "do-not-echo-endpoint-secret" not in bad_endpoint.text
    raw_credential = client.post(
        "/integration-connections",
        headers=headers,
        json=_connection_payload(
            workspace_id,
            credential_reference="do-not-echo-credential-secret",
        ),
    )
    assert raw_credential.status_code == 422
    assert "do-not-echo-credential-secret" not in raw_credential.text
    secret_configuration_reference = client.post(
        "/integration-connections",
        headers=headers,
        json=_connection_payload(
            workspace_id,
            configuration_reference=(
                "appconfig:integration?token=do-not-echo-configuration-secret"
            ),
        ),
    )
    assert secret_configuration_reference.status_code == 422
    assert "do-not-echo-configuration-secret" not in secret_configuration_reference.text
    secret_flag_metadata = client.put(
        "/integration-connections/feature-flags/geovision.integrations.construction.fake",
        headers=headers,
        json={
            "workspace_id": workspace_id,
            "enabled": True,
            "source": "azure_app_configuration",
            "configuration_reference": "appconfig:integration",
            "etag": "token=do-not-echo-flag-secret",
        },
    )
    assert secret_flag_metadata.status_code == 422
    assert "do-not-echo-flag-secret" not in secret_flag_metadata.text
    secret_extra_field = client.post(
        "/integration-connections",
        headers=headers,
        json={
            **_connection_payload(workspace_id),
            "do-not-echo-extra-field-secret": "rejected",
        },
    )
    assert secret_extra_field.status_code == 422
    assert "do-not-echo-extra-field-secret" not in secret_extra_field.text

    live = _create_connection(
        client,
        headers,
        workspace_id,
        connection_key="procore_primary",
        provider_code="procore",
        credential_reference=(
            "https://geovision-test.vault.azure.net/secrets/procore/token-v1"
        ),
    )
    enable = client.post(
        f"/integration-connections/{live['id']}/enable",
        headers=headers,
        json={"expected_version": live["version"]},
    )
    assert enable.status_code == 409
    assert enable.json()["detail"]["code"] == "provider_not_approved"

    azure_missing_reference = client.put(
        "/integration-connections/feature-flags/geovision.integrations.construction.fake",
        headers=headers,
        json={
            "workspace_id": workspace_id,
            "enabled": True,
            "source": "azure_app_configuration",
        },
    )
    assert azure_missing_reference.status_code == 422
    unrelated_flag = client.put(
        "/integration-connections/feature-flags/geovision.authorization.override",
        headers=headers,
        json={
            "workspace_id": workspace_id,
            "enabled": True,
            "source": "admin",
        },
    )
    assert unrelated_flag.status_code == 400
    assert unrelated_flag.json()["detail"]["code"] == "feature_flag_key_invalid"
    azure_flag = client.put(
        "/integration-connections/feature-flags/geovision.integrations.construction.fake",
        headers=headers,
        json={
            "workspace_id": workspace_id,
            "enabled": True,
            "source": "azure_app_configuration",
            "configuration_reference": "appconfig:geovision/integration/construction/fake",
            "etag": "etag-1",
            "configuration_version": "2026-09-10",
        },
    )
    assert azure_flag.status_code == 200, azure_flag.text
    assert azure_flag.json()["source"] == "azure_app_configuration"
    assert azure_flag.json()["etag"] == "etag-1"


def test_member_scoped_connections_are_private_and_health_requires_manage(
    client,
    db_session,
):
    owner = _user(db_session, "member-connection-owner")
    admin = _user(db_session, "member-connection-admin")
    viewer = _user(db_session, "member-connection-viewer")
    organization_id, workspace_id = _organization(
        client,
        db_session,
        owner,
        "Member Connection Boundaries",
    )
    owner_headers = _headers(owner, workspace_id)
    for member, role in ((admin, "admin"), (viewer, "viewer")):
        added = client.post(
            f"/organizations/{organization_id}/members",
            headers=owner_headers,
            json={"email": member.email, "user_id": member.id, "role": role},
        )
        assert added.status_code == 201, added.text

    member_connection = _create_connection(
        client,
        owner_headers,
        workspace_id,
        member_user_id=admin.id,
    )
    workspace_connection = _create_connection(client, owner_headers, workspace_id)

    owner_list = client.get(
        "/integration-connections",
        headers=owner_headers,
    )
    assert owner_list.status_code == 200
    assert member_connection["id"] not in {item["id"] for item in owner_list.json()}
    owner_read = client.get(
        f"/integration-connections/{member_connection['id']}",
        headers=owner_headers,
    )
    assert owner_read.status_code == 404
    owner_action = client.post(
        f"/integration-connections/{member_connection['id']}/enable",
        headers=owner_headers,
        json={"expected_version": member_connection["version"]},
    )
    assert owner_action.status_code == 404

    admin_headers = _headers(admin, workspace_id)
    admin_list = client.get("/integration-connections", headers=admin_headers)
    assert admin_list.status_code == 200
    assert {item["id"] for item in admin_list.json()} == {
        member_connection["id"],
        workspace_connection["id"],
    }
    enabled = client.post(
        f"/integration-connections/{member_connection['id']}/enable",
        headers=admin_headers,
        json={"expected_version": member_connection["version"]},
    )
    assert enabled.status_code == 200, enabled.text

    viewer_headers = _headers(viewer, workspace_id)
    visible = client.get(
        f"/integration-connections/{workspace_connection['id']}",
        headers=viewer_headers,
    )
    assert visible.status_code == 200
    forbidden_health = client.post(
        f"/integration-connections/{workspace_connection['id']}/health",
        headers=viewer_headers,
    )
    assert forbidden_health.status_code == 404


def test_organization_connection_sync_history_is_bound_to_active_workspace(
    client,
    db_session,
):
    owner = _user(db_session, "organization-connection-owner")
    organization_id, first_workspace_id = _organization(
        client,
        db_session,
        owner,
        "Organization Connection",
    )
    first_headers = _headers(owner, first_workspace_id)
    second_workspace_response = client.post(
        f"/organizations/{organization_id}/workspaces",
        headers=first_headers,
        json={
            "name": "Organization Connection Secondary",
            "customer_type": "construction",
            "sector_focus": "construction",
        },
    )
    assert second_workspace_response.status_code == 201, second_workspace_response.text
    second_workspace_id = second_workspace_response.json()["id"]
    second_headers = _headers(owner, second_workspace_id)

    organization_payload = _connection_payload(first_workspace_id)
    organization_payload["workspace_id"] = None
    organization_connection_response = client.post(
        "/integration-connections",
        headers=first_headers,
        json=organization_payload,
    )
    assert organization_connection_response.status_code == 201
    connection = organization_connection_response.json()
    _put_flag(client, first_headers, first_workspace_id, connection)
    _put_flag(client, second_headers, second_workspace_id, connection)
    connection = _enable(client, first_headers, connection)

    selectable = client.get(
        f"/integration-connections/{connection['id']}",
        headers=second_headers,
    )
    assert selectable.status_code == 200
    assert selectable.json()["workspace_id"] is None

    first_payload = {
        "direction": "inbound",
        "operation": "synchronize_project",
        "idempotency_key": "organization-sync-shared-key",
        "simulation_outcome": "success",
    }
    first_run_response = client.post(
        f"/integration-connections/{connection['id']}/sync-runs",
        headers=first_headers,
        json=first_payload,
    )
    assert first_run_response.status_code == 201, first_run_response.text
    first_run = first_run_response.json()
    assert first_run["workspace_id"] == first_workspace_id

    duplicate = client.post(
        f"/integration-connections/{connection['id']}/sync-runs",
        headers=first_headers,
        json=first_payload,
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == first_run["id"]
    cross_workspace_key = client.post(
        f"/integration-connections/{connection['id']}/sync-runs",
        headers=second_headers,
        json=first_payload,
    )
    assert cross_workspace_key.status_code == 201, cross_workspace_key.text
    second_run = cross_workspace_key.json()
    assert second_run["id"] != first_run["id"]
    assert second_run["workspace_id"] == second_workspace_id

    retry_run_response = client.post(
        f"/integration-connections/{connection['id']}/sync-runs",
        headers=first_headers,
        json={
            "direction": "inbound",
            "operation": "synchronize_project",
            "idempotency_key": "organization-sync-retry-key",
            "simulation_outcome": "unavailable",
        },
    )
    assert retry_run_response.status_code == 201, retry_run_response.text
    retry_run = retry_run_response.json()
    cross_workspace_retry = client.post(
        f"/integration-connections/{connection['id']}/sync-runs/"
        f"{retry_run['id']}/retry",
        headers=second_headers,
        json={
            "expected_version": retry_run["version"],
            "simulation_outcome": "success",
        },
    )
    assert cross_workspace_retry.status_code == 404
    assert cross_workspace_retry.json()["detail"]["code"] == "sync_run_not_found"

    first_runs = client.get(
        f"/integration-connections/{connection['id']}/sync-runs",
        headers=first_headers,
    )
    second_runs = client.get(
        f"/integration-connections/{connection['id']}/sync-runs",
        headers=second_headers,
    )
    assert {row["id"] for row in first_runs.json()} == {
        first_run["id"],
        retry_run["id"],
    }
    assert {row["id"] for row in second_runs.json()} == {second_run["id"]}
    hidden_events = client.get(
        f"/integration-connections/{connection['id']}/sync-events",
        headers=second_headers,
        params={"run_id": first_run["id"]},
    )
    assert hidden_events.status_code == 404
    assert hidden_events.json()["detail"]["code"] == "sync_run_not_found"


def test_feature_flag_writes_require_current_version(client, db_session):
    owner = _user(db_session, "atomic-feature-flag-owner")
    _, workspace_id = _organization(
        client,
        db_session,
        owner,
        "Atomic Feature Flag",
    )
    headers = _headers(owner, workspace_id)
    connection = _create_connection(client, headers, workspace_id)
    created = _put_flag(client, headers, workspace_id, connection)

    current = _put_flag(
        client,
        headers,
        workspace_id,
        connection,
        enabled=False,
        expected_version=created["version"],
    )
    assert current["version"] == created["version"] + 1
    stale_update = client.put(
        f"/integration-connections/feature-flags/{_flag_key(connection)}",
        headers=headers,
        json={
            "workspace_id": workspace_id,
            "enabled": True,
            "source": "admin",
            "expected_version": created["version"],
        },
    )
    assert stale_update.status_code == 409
    assert stale_update.json()["detail"]["code"] == "feature_flag_version_conflict"
    rows = client.get(
        "/integration-connections/feature-flags",
        headers=headers,
    )
    assert rows.status_code == 200
    assert rows.json()[0]["enabled"] is False
    assert rows.json()[0]["version"] == current["version"]

    stale_delete = client.delete(
        f"/integration-connections/feature-flags/overrides/{current['id']}",
        headers=headers,
        params={"expected_version": created["version"]},
    )
    assert stale_delete.status_code == 409
    deleted = client.delete(
        f"/integration-connections/feature-flags/overrides/{current['id']}",
        headers=headers,
        params={"expected_version": current["version"]},
    )
    assert deleted.status_code == 204, deleted.text
