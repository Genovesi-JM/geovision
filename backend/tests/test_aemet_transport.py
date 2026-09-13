"""Offline AEMET transport guards; use the isolated no-dotenv test runner."""
from datetime import datetime
import json

import httpx
import pytest

from app.integrations.weather.aemet import AemetOpenDataProvider

BASE = "https://opendata.aemet.es/opendata"
KEY = "synthetic-aemet-secret-never-live"
DATA = BASE + "/sh/temporary-data"
ROW = {"idema": "3195", "lat": 40.42, "lon": -3.70,
       "fint": "2026-09-13T04:00:00Z", "ta": 20.5, "hr": 60}
QUERY = {"latitude": 40.42, "longitude": -3.70,
         "starts_at": datetime(2026, 9, 12), "ends_at": datetime(2026, 9, 14)}


def adapter(handler, **kwargs):
    client = httpx.Client(transport=httpx.MockTransport(handler),
                         headers={"api_key": KEY, "Authorization": "Bearer synthetic-other",
                                  "Cookie": "synthetic=private"})
    return AemetOpenDataProvider(base_url=BASE, api_key=KEY, client=client,
                                retry_attempts=1, station_id="3195", **kwargs)


def test_fixed_station_key_only_first_step_and_finite_metrics():
    calls = []
    def handler(request):
        calls.append(request)
        assert request.headers["Accept-Encoding"] == "identity"
        assert "authorization" not in request.headers and "cookie" not in request.headers
        if len(calls) == 1:
            assert str(request.url) == BASE + "/api/observacion/convencional/datos/estacion/3195"
            assert request.headers["api_key"] == KEY
            return httpx.Response(200, json={"estado": 200, "datos": DATA})
        assert str(request.url) == DATA and "api_key" not in request.headers
        return httpx.Response(200, json=[dict(ROW, vv="inf", pres="-inf")])
    result = adapter(handler).observations(QUERY)
    assert result.ok and len(calls) == 2
    assert len(result.value) == 1
    assert {m.metric for m in result.value[0].metrics} == {"air_temperature", "relative_humidity"}


@pytest.mark.parametrize("url", [
    "https://other.example/opendata/sh/data", "http://opendata.aemet.es/opendata/sh/data",
    BASE.replace(".es", ".es:444") + "/sh/data", "https://u:p@opendata.aemet.es/opendata/sh/data",
    BASE + "/api/other", BASE + "/sh/data?key=private", BASE + "/sh/data#fragment",
    BASE + "/sh/%2e%2e", BASE + "/sh/../data", BASE + "/sh/data/more",
    BASE + "/sh/a\\b", BASE + "/sh/a\nb", BASE + "/sh/data?", BASE + "/sh/data#",
])
def test_data_destination_rejected_before_second_request(url):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"estado": 200, "datos": url})
    result = adapter(handler).observations(QUERY)
    assert not result.ok and len(calls) == 1
    assert KEY not in str(result.failure)


@pytest.mark.parametrize("base", [
    "https://other.example/opendata", "http://opendata.aemet.es/opendata",
    BASE + "?x=y", BASE + "#f", "https://u:p@opendata.aemet.es/opendata",
    BASE.replace(".es", ".es:444"), BASE + "/other", BASE + "\n",
])
def test_constructor_rejects_untrusted_base(base):
    with pytest.raises(ValueError, match="official HTTPS origin"):
        AemetOpenDataProvider(base_url=base, api_key=KEY)


@pytest.mark.parametrize("status", [302, 401, 429, 500])
def test_provider_errors_not_followed_or_retried(status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={"Location": "https://other.example/private"}, text=KEY)
    result = adapter(handler).observations(QUERY)
    assert not result.ok and len(calls) == 1
    assert KEY not in str(result.failure)


@pytest.mark.parametrize("headers,body", [
    ({"Content-Encoding": "gzip"}, b"encoded"),
    ({"Content-Length": "2049"}, b"small"),
    ({"Content-Length": "invalid"}, b"small"),
    ({}, b"x" * 2049),
])
def test_response_limits(headers, body):
    calls = []
    def handler(request):
        calls.append(request)
        # Raw streamed fixture avoids httpx pre-decoding a synthetic gzip body.
        return httpx.Response(200, headers=headers, stream=httpx.ByteStream(body))
    result = adapter(handler, max_response_bytes=2048).observations(QUERY)
    assert not result.ok and len(calls) == 1


def test_data_response_is_bounded_too():
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={"estado": 200, "datos": DATA})
        return httpx.Response(200, stream=httpx.ByteStream(b"x" * 2049))
    result = adapter(handler, max_response_bytes=2048).observations(QUERY)
    assert not result.ok and len(calls) == 2


@pytest.mark.parametrize("row", [dict(ROW, lat="inf"), dict(ROW, lon=300), dict(ROW, idema="OTHER"),
                                  dict(ROW, fint="2000-01-01T00:00:00Z")])
def test_invalid_stale_or_wrong_station_is_not_success(row):
    def handler(request):
        return httpx.Response(200, json=[row] if request.url.path.startswith("/opendata/sh/")
                              else {"estado": 200, "datos": DATA})
    assert not adapter(handler).observations(QUERY).ok


def test_default_client_rejects_proxy_inheritance(monkeypatch):
    original = httpx.Client.__init__
    seen = []
    def wrapped(self, **kwargs):
        seen.append(kwargs)
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        assert KEY not in json.dumps(kwargs["headers"])
        original(self, **kwargs)
    monkeypatch.setattr(httpx.Client, "__init__", wrapped)
    provider = AemetOpenDataProvider(base_url=BASE, api_key=KEY)
    provider.client.close()
    assert len(seen) == 1
