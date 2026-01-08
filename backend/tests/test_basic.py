
import os
import sys

# Ensure the `backend` folder is on sys.path so imports like `import app` resolve
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
# Ensure the app uses the backend/geovision.db (we modified that DB during local fixes).
# The application reads `database_url` from settings; set an env var override before importing.
os.environ.setdefault("DATABASE_URL", "sqlite:///./backend/geovision.db")

from app.main import app
from fastapi.testclient import TestClient


client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_demo_login():
    # demo seeded credentials used by the project
    payload = {"email": "teste@admin.com", "password": "123456"}
    r = client.post("/auth/login", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    # API returns an access_token and user info for the demo seed
    assert "access_token" in data
    assert data.get("email") == "teste@admin.com"


def test_register_and_login():
    import uuid

    unique = uuid.uuid4().hex[:8]
    email = f"reg-{unique}@example.com"
    password = "strong-pass-123"

    # Register
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    data = r.json()
    assert "access_token" in data
    assert data.get("email") == email

    # Login with same credentials
    r2 = client.post("/auth/login", json={"email": email, "password": password})
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert "access_token" in d2
    assert d2.get("email") == email
