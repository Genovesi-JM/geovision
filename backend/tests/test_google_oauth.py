import json, sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from app.config import settings


class DummyResp:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code
        self.text = json.dumps(data)

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


def test_google_flow_monkeypatch(monkeypatch, tmp_path):
    # ensure Google OAuth is configured for the test
    settings.google_client_id = "TEST_CLIENT_ID"
    settings.google_client_secret = "TEST_CLIENT_SECRET"
    # backend_base should match TestClient base
    settings.backend_base = "http://testserver"

    # Import application and DB artifacts here (after conftest has set the
    # test database URL). Importing at module level can cause engines to be
    # created with the default DB before the test fixture overrides it.
    from app.main import create_application
    from app.database import SessionLocal
    from app.models import OAuthState, User

    app = create_application()
    client = TestClient(app)

    # 1) Call /auth/google/login and ensure redirect contains state
    assert client.get('/auth/google/login', follow_redirects=False).status_code == 422
    browser_nonce = 'a' * 64
    resp = client.get(
        '/auth/google/login',
        params={'browser_nonce': browser_nonce},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    loc = resp.headers.get('location')
    assert 'accounts.google.com' in loc
    assert 'state=' in loc

    # extract state param
    import urllib.parse as up
    qs = up.urlparse(loc).query
    params = dict(up.parse_qsl(qs))
    state = params.get('state')
    assert state
    assert params.get('code_challenge_method') == 'S256'
    assert params.get('code_challenge')

    # ensure DB has OAuthState
    db = SessionLocal()
    st = db.query(OAuthState).filter(OAuthState.state == state).first()
    assert st is not None
    assert not st.used
    assert st.provider == 'google'
    assert st.code_verifier

    # 2) Mock token exchange and userinfo
    token_requests = []

    def fake_post(url, data=None, timeout=None, allow_redirects=None):
        assert allow_redirects is False
        token_requests.append((url, data))
        return DummyResp({"access_token": "FAKE_GOOGLE_ACCESS"})

    def fake_get(url, headers=None, timeout=None, allow_redirects=None):
        assert allow_redirects is False
        assert headers == {"Authorization": "Bearer FAKE_GOOGLE_ACCESS"}
        return DummyResp({
            "id": "google-subject-test-user",
            "email": "test-google@example.com",
            "verified_email": True,
            "name": "Test User",
        })

    monkeypatch.setattr('requests.post', fake_post)
    monkeypatch.setattr('requests.get', fake_get)

    # A transferred callback URL is not enough: the initiating browser's
    # HttpOnly state cookie is also required, before any token exchange occurs.
    victim = TestClient(app)
    rejected = victim.get(
        '/auth/google/callback',
        params={'code': 'attacker-code', 'state': state},
        follow_redirects=False,
    )
    assert rejected.status_code == 400
    assert token_requests == []

    # Call callback with code and state
    cb = client.get(
        '/auth/google/callback',
        params={'code': 'abc', 'state': state},
        follow_redirects=False,
    )
    assert cb.status_code in (302, 307)
    assert token_requests[0][1]['code_verifier'] == st.code_verifier
    callback_location = cb.headers['location']
    assert '/auth-callback.html' in callback_location
    assert '#token=' in callback_location
    assert 'provider=google' in callback_location
    assert f'browser_nonce={browser_nonce}' in callback_location

    # Verify user created in DB using a fresh SessionLocal (engine is
    # initialized by conftest so visibility should be consistent).
    db.close()
    db2 = SessionLocal()
    user = db2.query(User).filter(User.email == 'test-google@example.com').first()
    assert user is not None
    db2.close()
