from __future__ import annotations

from io import StringIO
import json
import logging
import sys
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.observability import (
    JsonLogFormatter,
    bind_context,
    configure_observability,
    log_event,
    reset_context,
    safe_identifier,
    sanitize_fields,
)
from app.middleware import RequestContextMiddleware


def test_recursive_log_sanitizer_redacts_common_secret_shapes():
    sanitized = sanitize_fields(
        {
            "authorization": "Bearer private",
            "nested": {
                "apiKey": "private-key",
                "clientSecret": "private-secret",
                "safe": "visible",
            },
        }
    )

    assert sanitized == {
        "authorization": "[redacted]",
        "nested": {
            "apiKey": "[redacted]",
            "clientSecret": "[redacted]",
            "safe": "visible",
        },
    }


def test_json_formatter_carries_trace_scope_without_secret_values():
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    logger = logging.getLogger("test.observability")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    token = bind_context(
        request_id="request-123",
        correlation_id="correlation-456",
        organization_id="org-789",
        asset_id="asset-012",
    )
    try:
        log_event(
            logger,
            logging.INFO,
            "processing.job.completed",
            processing_job_id="job-345",
            api_key="must-not-appear",
        )
    finally:
        reset_context(token)

    payload = json.loads(stream.getvalue())
    assert payload["event"] == "processing.job.completed"
    assert payload["request_id"] == "request-123"
    assert payload["correlation_id"] == "correlation-456"
    assert payload["organization_id"] == "org-789"
    assert payload["asset_id"] == "asset-012"
    assert payload["processing_job_id"] == "job-345"
    assert payload["api_key"] == "[redacted]"
    assert "must-not-appear" not in stream.getvalue()


def test_request_context_accepts_safe_ids_and_replaces_header_injection():
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/assets/{asset_id}")
    def endpoint(asset_id: str):
        return {"asset_id": asset_id}

    with TestClient(app) as client:
        accepted = client.get(
            "/assets/asset-1",
            headers={
                "X-Request-ID": "request.safe-1",
                "X-Correlation-ID": "correlation:safe-2",
            },
        )
        replaced = client.get(
            "/assets/asset-2",
            headers={"X-Request-ID": "unsafe header"},
        )

    assert accepted.headers["X-Request-ID"] == "request.safe-1"
    assert accepted.headers["X-Correlation-ID"] == "correlation:safe-2"
    assert replaced.headers["X-Request-ID"] != "unsafe header"
    assert safe_identifier(replaced.headers["X-Request-ID"])
    assert replaced.headers["X-Correlation-ID"] == replaced.headers["X-Request-ID"]


def test_azure_monitor_configuration_falls_back_without_credentials():
    result = configure_observability(
        SimpleNamespace(
            log_level="INFO",
            observability_exporter="azure_monitor",
            applicationinsights_connection_string=None,
        )
    )

    assert result == {
        "exporter": "azure_monitor",
        "structured_logging": True,
        "azure_monitor_configured": False,
        "fallback_reason": "connection_string_not_configured",
    }


def test_azure_monitor_configuration_falls_back_when_exporter_is_unavailable(
    monkeypatch,
):
    monkeypatch.setitem(sys.modules, "azure.monitor.opentelemetry", None)

    result = configure_observability(
        SimpleNamespace(
            log_level="INFO",
            observability_exporter="azure_monitor",
            applicationinsights_connection_string=(
                "InstrumentationKey=00000000-0000-0000-0000-000000000000"
            ),
        )
    )

    assert result == {
        "exporter": "azure_monitor",
        "structured_logging": True,
        "azure_monitor_configured": False,
        "fallback_reason": "azure_monitor_exporter_unavailable",
    }
