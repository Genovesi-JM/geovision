from app.main import create_application
from fastapi.testclient import TestClient
from app.config import settings
import requests

settings.google_client_id = 'TEST_ID'
settings.google_client_secret = 'TEST_SECRET'
settings.backend_base = 'http://testserver'

app = create_application()
client = TestClient(app)

resp = client.get('/auth/google/login', allow_redirects=False)
print('login resp', resp.status_code, resp.headers.get('location'))
loc = resp.headers.get('location')
import urllib.parse as up
qs = up.urlparse(loc).query
params = dict(up.parse_qsl(qs))
state = params.get('state')
print('state', state)

class DummyResp:
    def __init__(self, data):
        self._data = data
    def raise_for_status(self):
        return None
    def json(self):
        return self._data


requests.post = lambda url, data=None, timeout=None: DummyResp({'access_token':'FAKE'})
requests.get = lambda url, params=None, timeout=None: DummyResp({'email':'dbg@example.com','name':'DBG'})

try:
    cb = client.get('/auth/google/callback', params={'code':'abc','state':state})
    print('callback status', cb.status_code)
    print(cb.text)
except Exception as exc:
    import traceback
    traceback.print_exc()

