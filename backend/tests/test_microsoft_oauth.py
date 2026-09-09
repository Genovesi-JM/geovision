from __future__ import annotations

from urllib.parse import parse_qs, urlsplit
import uuid

from fastapi.testclient import TestClient

from app.core.config import settings
from app.models import AuthIdentity, User


class DummyResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data


def _start_microsoft_login(client: TestClient, browser_nonce: str):
    response = client.get(
        "/auth/microsoft/login",
        params={"browser_nonce": browser_nonce},
        follow_redirects=False,
    )
    assert response.status_code in (302, 307), response.text
    location = response.headers["location"]
    params = parse_qs(urlsplit(location).query)
    assert params["code_challenge_method"] == ["S256"]
    assert params["code_challenge"][0]
    return params["state"][0]


def test_microsoft_callback_preserves_returning_mapping_and_rejects_replay(
    monkeypatch,
):
    tenant_id = "55555555-5555-4555-8555-555555555555"
    browser_nonce = "m" * 64
    microsoft_subject = f"microsoft-{uuid.uuid4()}"
    email = f"returning-microsoft-{uuid.uuid4().hex}@example.com"
    monkeypatch.setattr(settings, "microsoft_client_id", "microsoft-client")
    monkeypatch.setattr(settings, "microsoft_client_secret", "microsoft-secret")
    monkeypatch.setattr(settings, "microsoft_tenant_id", tenant_id)
    monkeypatch.setattr(settings, "backend_base", "http://testserver")

    from app.database import SessionLocal
    from app.main import create_application

    db = SessionLocal()
    try:
        user = User(email=email, password_hash=None, role="cliente", is_active=True)
        db.add(user)
        db.flush()
        original_user_id = user.id
        db.add(
            AuthIdentity(
                user_id=user.id,
                provider="microsoft",
                provider_user_id=microsoft_subject,
                email=email,
            )
        )
        db.commit()
    finally:
        db.close()

    token_calls = []

    def fake_post(url, data=None, timeout=None, allow_redirects=None):
        assert tenant_id in url
        assert allow_redirects is False
        assert data["code_verifier"]
        token_calls.append(data.copy())
        return DummyResponse({"access_token": "microsoft-graph-access"})

    def fake_get(url, headers=None, timeout=None, allow_redirects=None):
        assert url == "https://graph.microsoft.com/v1.0/me"
        assert headers == {"Authorization": "Bearer microsoft-graph-access"}
        assert allow_redirects is False
        return DummyResponse(
            {
                "id": microsoft_subject,
                "mail": email,
                "displayName": "Returning Microsoft User",
            }
        )

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("requests.get", fake_get)
    app = create_application()
    with TestClient(app) as client:
        assert client.get(
            "/auth/microsoft/login",
            follow_redirects=False,
        ).status_code == 422
        state = _start_microsoft_login(client, browser_nonce)
        callback = client.get(
            "/auth/microsoft/callback",
            params={"code": "microsoft-code", "state": state},
            follow_redirects=False,
        )
        replay = client.get(
            "/auth/microsoft/callback",
            params={"code": "microsoft-code", "state": state},
            follow_redirects=False,
        )

    assert callback.status_code in (302, 307), callback.text
    location = callback.headers["location"]
    assert "/auth-callback.html?v=8#" in location
    assert "provider=microsoft" in location
    assert f"browser_nonce={browser_nonce}" in location
    assert replay.status_code == 400
    assert len(token_calls) == 1

    db = SessionLocal()
    try:
        identity = (
            db.query(AuthIdentity)
            .filter(AuthIdentity.provider_user_id == microsoft_subject)
            .one()
        )
        assert identity.user_id == original_user_id
        assert identity.issuer == "legacy:microsoft"
        assert identity.subject == microsoft_subject
        assert db.query(User).filter(User.email == email).count() == 1
    finally:
        db.close()


def test_microsoft_callback_does_not_provision_from_graph_email(monkeypatch):
    tenant_id = "66666666-6666-4666-8666-666666666666"
    browser_nonce = "n" * 64
    email = f"unlinked-microsoft-{uuid.uuid4().hex}@example.com"
    monkeypatch.setattr(settings, "microsoft_client_id", "microsoft-client")
    monkeypatch.setattr(settings, "microsoft_client_secret", "microsoft-secret")
    monkeypatch.setattr(settings, "microsoft_tenant_id", tenant_id)
    monkeypatch.setattr(settings, "backend_base", "http://testserver")

    def fake_post(url, data=None, timeout=None, allow_redirects=None):
        assert allow_redirects is False
        return DummyResponse({"access_token": "microsoft-graph-access"})

    def fake_get(url, headers=None, timeout=None, allow_redirects=None):
        assert allow_redirects is False
        return DummyResponse(
            {
                "id": f"unlinked-{uuid.uuid4()}",
                "userPrincipalName": email,
                "displayName": "Unlinked Microsoft User",
            }
        )

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("requests.get", fake_get)

    from app.database import SessionLocal
    from app.main import create_application

    app = create_application()
    with TestClient(app) as client:
        state = _start_microsoft_login(client, browser_nonce)
        callback = client.get(
            "/auth/microsoft/callback",
            params={"code": "microsoft-code", "state": state},
            follow_redirects=False,
        )

    assert callback.status_code == 400
    db = SessionLocal()
    try:
        assert db.query(User).filter(User.email == email).count() == 0
    finally:
        db.close()
