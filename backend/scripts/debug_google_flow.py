from app.main import create_application
from fastapi.testclient import TestClient
from app.config import settings
import requests
import secrets

settings.google_client_id = 'TEST_ID'
settings.google_client_secret = 'TEST_SECRET'
settings.backend_base = 'http://testserver'

app = create_application()
client = TestClient(app)

browser_nonce = secrets.token_urlsafe(48)
resp = client.get(
    '/auth/google/login',
    params={'browser_nonce': browser_nonce},
    follow_redirects=False,
)
print('login resp', resp.status_code, resp.headers.get('location'))
loc = resp.headers.get('location')
import urllib.parse as up
qs = up.urlparse(loc).query
params = dict(up.parse_qsl(qs))
state = params.get('state')
print('state', state)

class DummyResp:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code
    def raise_for_status(self):
        return None
    def json(self):
        return self._data


requests.post = lambda url, **kwargs: DummyResp({'access_token':'FAKE'})
requests.get = lambda url, **kwargs: DummyResp({
    'id': 'google-debug-subject',
    'email': 'dbg@example.com',
    'verified_email': True,
    'name': 'DBG',
})

try:
    cb = client.get(
        '/auth/google/callback',
        params={'code':'abc','state':state},
        follow_redirects=False,
    )
    print('callback status', cb.status_code)
    print(cb.text)
except Exception as exc:
    import traceback
    traceback.print_exc()
