import uuid


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


def test_delete_account_removes_user_and_blocks_reuse_of_token(client):
    email = f"del-{uuid.uuid4().hex[:8]}@example.com"
    body = _register(client, email)
    token = body["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Sanity: the account exists and is reachable.
    assert client.get("/auth/me", headers=headers).status_code == 200

    # Delete the account.
    deleted = client.request("DELETE", "/auth/account", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"success": True, "deleted": True}

    # The user no longer exists — /auth/me now 404s for the same token.
    assert client.get("/auth/me", headers=headers).status_code == 404

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
