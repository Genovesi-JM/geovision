from decimal import Decimal
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.core.tokens import create_user_access_token
from app.models import ProviderUsage, User
from app.routers import ai as ai_router


def test_gaia_demo_explains_indoor_agriculture_without_provider_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # Settings loads backend/.env once at import time, so clearing only the
    # process environment is insufficient on a developer machine with a key.
    monkeypatch.setattr(settings, "openai_api_key", None)
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


def test_gaia_demo_resolves_short_area_name_from_authorized_app_context(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(settings, "openai_api_key", None)
    with TestClient(app) as client:
        response = client.post(
            "/ai/chat",
            json={
                "messages": [{"role": "user", "content": "Bloco A maize"}],
                "page": "/mobile/site",
                "page_title": "GeoVision mobile · site",
                "sector": "Agricultura",
                "page_text": (
                    "AUTHORIZED APP CONTEXT (customer-visible data only)\n"
                    "Selected site: Kilombo North Fields | Malanje, Angola | 142 ha.\n"
                    "Area: Block A — Maize | crop Maize | 48.0 ha | Average NDVI 0.72 (ok), Water stress 23% (warning)."
                ),
            },
        )

    assert response.status_code == 200
    reply = response.json()["reply"]
    assert "Block A" in reply
    assert "48.0 ha" in reply
    assert "mais detalhes" not in reply.lower()


def test_external_ai_requires_customer_scope_and_meters_tokens(
    client, db_session, monkeypatch
):
    user = User(
        id=str(uuid.uuid4()),
        email=f"ai-{uuid.uuid4().hex}@example.test",
        role="cliente",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    token = create_user_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        auth_generation=user.auth_generation,
    )
    base_headers = {"Authorization": f"Bearer {token}"}
    monkeypatch.setattr(settings, "openai_api_key", "test-provider-key")

    called = False

    async def provider(*_args, **_kwargs):
        nonlocal called
        called = True
        return "Validated answer", {
            "response_id": "response-phase-25",
            "model": "gpt-test-2026-09-10",
            "system_fingerprint": "fp-test",
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 5,
                "total_tokens": 17,
            },
        }

    monkeypatch.setattr(ai_router, "call_openai", provider)
    denied = client.post(
        "/ai/chat",
        headers=base_headers,
        json={"messages": [{"role": "user", "content": "Summarize this asset"}]},
    )
    assert denied.status_code == 403
    assert called is False

    organization = client.post(
        "/organizations",
        headers=base_headers,
        json={
            "name": f"AI customer {uuid.uuid4().hex[:8]}",
            "country": "Angola",
            "workspace": {
                "name": "AI workspace",
                "customer_type": "business",
                "sector_focus": "agro",
            },
        },
    )
    assert organization.status_code == 201, organization.text
    workspace_id = organization.json()["workspaces"][0]["id"]
    scoped = client.post(
        "/ai/chat",
        headers={**base_headers, "X-Workspace-ID": workspace_id},
        json={"messages": [{"role": "user", "content": "Summarize this asset"}]},
    )
    assert scoped.status_code == 200, scoped.text
    assert scoped.json()["reply"] == "Validated answer"

    usage = db_session.query(ProviderUsage).filter_by(provider="openai").one()
    assert usage.workspace_id == workspace_id
    assert usage.service == "chat_completions"
    assert usage.usage_type == "ai_tokens"
    assert usage.quantity == Decimal("17")
    assert usage.provider_reference == "response-phase-25"
    assert "test-provider-key" not in usage.metadata_json
