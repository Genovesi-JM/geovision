"""Offline contracts; run with dotenv disabled before importing the app."""
import json
from types import SimpleNamespace

import httpx
import pytest

from app.modules.operations.provider_readiness import (
    PROVIDERS, provider_inventory, public_provider_check,
)


@pytest.fixture(autouse=True)
def isolate_check_limits(monkeypatch):
    from app.modules.operations import provider_readiness as module
    monkeypatch.setattr(module, "MIN_CHECK_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(module, "_LAST_CHECK", {})


def config(**overrides):
    summary = {"configured": overrides.pop("configured", {}), "providers": overrides.pop("providers", {})}
    return SimpleNamespace(safe_summary=lambda: summary, gis_provider="miteco", satellite_provider="copernicus", **overrides)


def test_inventory_is_complete_unique_and_never_claims_live():
    result = provider_inventory(config())
    assert len(result["items"]) == len(PROVIDERS) >= 39
    assert len({item["key"] for item in result["items"]}) == len(PROVIDERS)
    assert all(item["verification"] == "not_checked" for item in result["items"])
    assert not any(item["public_check_available"] for item in result["items"])
    assert not any("live" in item["state"] for item in result["items"])


def test_credentials_do_not_make_scaffolds_or_payments_live():
    items = {item["key"]: item for item in provider_inventory(config(
        configured={"stripe": True, "arcgis": True, "openai": True, "unknown_secret": "synthetic-secret-canary"},
        providers={"gis": "arcgis", "report_narrative": "openai"})) ["items"]}
    assert items["arcgis"]["state"] == "not_implemented"
    assert items["external_narrative"]["state"] == "not_implemented"
    assert items["stripe"]["state"] == "configured_unverified"
    assert items["stripe"]["selected"] is None
    assert "synthetic-secret-canary" not in json.dumps(items)


def test_public_selection_enables_only_explicit_checks():
    items = {item["key"]: item for item in provider_inventory(config(providers={"gis": "miteco", "satellite": "copernicus"}))["items"]}
    assert items["miteco"]["public_check_available"] is True
    assert items["copernicus"]["public_check_available"] is True
    assert items["copernicus"]["state"] == "configured_unverified"
    assert not items["stripe"]["public_check_available"]


def wire(monkeypatch, handler):
    original = httpx.Client.__init__
    def init(self, *args, **kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        assert kwargs["headers"]["Accept-Encoding"] == "identity"
        kwargs["transport"] = httpx.MockTransport(handler)
        original(self, *args, **kwargs)
    monkeypatch.setattr(httpx.Client, "__init__", init)


def test_miteco_empty_is_not_coverage(monkeypatch):
    seen = []
    def handler(request):
        seen.append(request)
        assert request.url.host == "gis.miteco.gob.es"
        assert request.method == "GET"
        assert request.url.params["limit"] == "1"
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"type": "FeatureCollection", "features": [], "numberReturned": 0})
    wire(monkeypatch, handler)
    result = public_provider_check("miteco", config())
    assert result["status"] == "reachable_no_data"
    assert result["records"] == 0 and result["context_only"] is True
    assert len(seen) == 1


def test_copernicus_public_scene_response(monkeypatch):
    def handler(request):
        assert str(request.url) == "https://stac.dataspace.copernicus.eu/v1/search"
        assert "authorization" not in request.headers
        data = json.loads(request.content)
        assert data["limit"] == 2 and data["collections"] == ["sentinel-2-l2a"]
        return httpx.Response(200, json={"type": "FeatureCollection", "features": [{
            "id": "synthetic-scene", "collection": "sentinel-2-l2a", "geometry": None,
            "properties": {"datetime": "2026-09-12T12:00:00Z"}, "assets": {},
        }]})
    wire(monkeypatch, handler)
    result = public_provider_check("copernicus", config())
    assert result["status"] == "response_verified" and result["records"] == 1
    assert "synthetic-scene" not in json.dumps(result)


@pytest.mark.parametrize("status", [302, 401, 429, 500])
def test_failed_provider_is_not_retried_or_leaked(monkeypatch, status):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(status, text="synthetic-secret-canary", headers={"location": "https://unapproved.example.test"})
    wire(monkeypatch, handler)
    result = public_provider_check("copernicus", config())
    assert result["status"] == "failed"
    assert "synthetic-secret-canary" not in json.dumps(result)
    assert len(seen) == 1


def test_oversized_response_is_rejected(monkeypatch):
    wire(monkeypatch, lambda _: httpx.Response(200, content=b"x" * (2 * 1024 * 1024 + 1)))
    assert public_provider_check("copernicus", config())["status"] == "failed"


def test_check_cooldown(monkeypatch):
    from app.modules.operations import provider_readiness as module
    monkeypatch.setattr(module, "MIN_CHECK_INTERVAL_SECONDS", 30)
    wire(monkeypatch, lambda _: httpx.Response(200, json={"type": "FeatureCollection", "features": []}))
    assert public_provider_check("copernicus", config())["status"] == "reachable_no_data"
    with pytest.raises(ValueError, match="public_check_cooldown"):
        public_provider_check("copernicus", config())


@pytest.mark.parametrize("provider", ["stripe", "../copernicus", "https://example.test", "smtp"])
def test_other_providers_are_never_called(provider):
    with pytest.raises(ValueError, match="unsupported_public_check"):
        public_provider_check(provider, config())


def test_not_selected_refuses_io():
    with pytest.raises(ValueError, match="provider_not_selected"):
        public_provider_check("copernicus", SimpleNamespace(satellite_provider="none", gis_provider="none"))


def test_routes_enforce_platform_admin_and_reject_input(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routers import operations_experience as routes
    from app.modules.operations.auth import require_internal_actor
    app = FastAPI()
    app.include_router(routes.router)
    actor = SimpleNamespace(id="synthetic-user")
    app.dependency_overrides[require_internal_actor] = lambda: actor
    app.dependency_overrides[routes.get_db] = lambda: None
    permission = {"granted": False}
    monkeypatch.setattr(routes, "internal_actor_contract", lambda *_: ([], [], ["integrations"] if permission["granted"] else []))
    monkeypatch.setattr(routes, "settings", config())
    called = []
    monkeypatch.setattr(routes, "public_provider_check", lambda provider, _: called.append(provider) or {"status": "reachable_no_data"})
    with TestClient(app) as client:
        assert client.get("/operations/providers").status_code == 403
        assert client.post("/operations/providers/miteco/check", json={}).status_code == 403
        assert not called
        permission["granted"] = True
        assert client.get("/operations/providers").status_code == 200
        assert client.post("/operations/providers/miteco/check?url=foo", json={}).status_code == 400
        assert client.post("/operations/providers/miteco/check", json={"secret": "canary"}).status_code == 400
        assert client.post("/operations/providers/stripe/check", json={}).status_code == 404
        assert not called
        assert client.post("/operations/providers/miteco/check", json={}).status_code == 200
        assert called == ["miteco"]
