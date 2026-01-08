import json, sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from app.config import settings


class DummyResp:
    def __init__(self, data):
        self._data = data

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
    resp = client.get('/auth/google/login', allow_redirects=False)
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

    # ensure DB has OAuthState
    db = SessionLocal()
    st = db.query(OAuthState).filter(OAuthState.state == state).first()
    assert st is not None
    assert not st.used

    # 2) Mock token exchange and userinfo
    def fake_post(url, data=None, timeout=None):
        return DummyResp({"access_token": "FAKE_GOOGLE_ACCESS"})

    def fake_get(url, params=None, timeout=None):
        return DummyResp({"email": "test-google@example.com", "name": "Test User"})

    monkeypatch.setattr('requests.post', fake_post)
    monkeypatch.setattr('requests.get', fake_get)

    # Call callback with code and state
    cb = client.get('/auth/google/callback', params={'code': 'abc', 'state': state})
    assert cb.status_code == 200
    text = cb.text
    assert 'localStorage.setItem' in text
    assert 'test-google@example.com' in text

    # Verify user created in DB using a fresh SessionLocal (engine is
    # initialized by conftest so visibility should be consistent).
    db.close()
    db2 = SessionLocal()
    user = db2.query(User).filter(User.email == 'test-google@example.com').first()
    assert user is not None
    db2.close()
