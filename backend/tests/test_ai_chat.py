from fastapi.testclient import TestClient

from app.main import app


def test_gaia_demo_explains_indoor_agriculture_without_provider_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with TestClient(app) as client:
        response = client.post(
            "/ai/chat",
            json={
                "messages": [
                    {"role": "user", "content": "Como funciona agricultura indoor?"}
                ],
                "page": "/mobile/assistant",
                "page_title": "GeoVision mobile",
                "sector": "Agricultura indoor",
            },
        )

    assert response.status_code == 200
    reply = response.json()["reply"]
    assert "modulo" in reply
    assert "CO2" in reply
    assert "confirmacao humana" in reply
