import uuid

from app.models import RefreshTokenFamily, User


def _register(client, email):
    resp = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "strong-pass-123",
            "full_name": "Delete Me",
            "customer_type": "farm",
            "sectors": ["agro"],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_delete_account_removes_user_and_blocks_reuse_of_token(client, db_session):
    email = f"del-{uuid.uuid4().hex[:8]}@example.com"
    body = _register(client, email)
    token = body["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Sanity: the account exists and is reachable.
    assert client.get("/auth/me", headers=headers).status_code == 200

    # Delete the account.
    deleted = client.request(
        "DELETE",
        "/auth/account",
        headers=headers,
        json={"password": "strong-pass-123"},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"success": True, "deleted": True}

    # The signed token still parses, but its immutable user ID no longer maps
    # to an active account and must not fall back to the reusable email.
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert (
        db_session.query(RefreshTokenFamily)
        .filter(RefreshTokenFamily.user_id == body["user"]["id"])
        .count()
        == 0
    )

    stale_onboarding = client.post(
        "/auth/onboarding",
        headers=headers,
        json={"customer_type": "farm", "sectors": ["agro"]},
    )
    assert stale_onboarding.status_code == 401

    # The email is free to register again (fully removed).
    again = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "another-pass-456",
            "full_name": "Fresh Start",
            "customer_type": "farm",
            "sectors": ["agro"],
        },
    )
    assert again.status_code == 201, again.text


def test_delete_account_requires_auth(client):
    assert client.request("DELETE", "/auth/account").status_code == 401


def test_delete_account_requires_step_up_password(client):
    email = f"del-step-up-{uuid.uuid4().hex[:8]}@example.com"
    body = _register(client, email)
    headers = {"Authorization": f"Bearer {body['access_token']}"}

    rejected = client.request("DELETE", "/auth/account", headers=headers)

    assert rejected.status_code == 403
    assert client.get("/auth/me", headers=headers).status_code == 200


def test_delete_account_rejects_wrong_password_when_supplied(client):
    email = f"del2-{uuid.uuid4().hex[:8]}@example.com"
    body = _register(client, email)
    headers = {"Authorization": f"Bearer {body['access_token']}"}

    bad = client.request(
        "DELETE", "/auth/account", headers=headers, json={"password": "not-the-password"}
    )
    assert bad.status_code == 403, bad.text
    # Account survived the rejected attempt.
    assert client.get("/auth/me", headers=headers).status_code == 200


def test_delete_account_never_reports_success_after_transaction_failure(
    client,
    db_session,
    monkeypatch,
):
    email = f"del-fail-{uuid.uuid4().hex[:8]}@example.com"
    body = _register(client, email)
    user_id = body["user"]["id"]

    def fail_audit(*args, **kwargs):
        raise RuntimeError("simulated audit write failure")

    monkeypatch.setattr("app.routers.auth.log_audit", fail_audit)
    failed = client.request(
        "DELETE",
        "/auth/account",
        headers={"Authorization": f"Bearer {body['access_token']}"},
        json={"password": "strong-pass-123"},
    )

    assert failed.status_code == 409
    db_session.expire_all()
    assert db_session.get(User, user_id) is not None
