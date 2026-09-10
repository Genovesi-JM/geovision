"""Provider-neutral structured logging and request correlation.

The common layer intentionally depends only on the Python standard library.
Azure Monitor/OpenTelemetry wiring is optional and is activated at the
composition root when the corresponding package and configuration exist.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from datetime import date, datetime, timezone
import json
import logging
import math
import re
from typing import Any, Mapping


_CONTEXT: ContextVar[dict[str, Any]] = ContextVar(
    "geovision_observability_context", default={}
)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SENSITIVE_KEY = re.compile(
    r"(^|_)(authorization|cookie|credential|password|passwd|secret|token|api_key|"
    r"private_key|connection_string|sas_key|signature|client_secret)($|_)",
    re.IGNORECASE,
)
_STANDARD_RECORD_KEYS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)
_CONFIGURED = False


def safe_identifier(value: Any, *, fallback: str | None = None) -> str | None:
    """Accept a bounded opaque identifier and reject header/log injection."""

    candidate = str(value or "").strip()
    if not candidate or not _IDENTIFIER.fullmatch(candidate):
        return fallback
    return candidate


def sanitize_fields(value: Any, *, depth: int = 0) -> Any:
    """Return a JSON-safe, bounded value with credential-shaped fields redacted."""

    if depth > 10:
        return "[truncated]"
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, str):
        return value[:2_000]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, nested in list(value.items())[:200]:
            key = str(raw_key)[:160]
            normalized = re.sub(
                r"(?<=[a-z0-9])(?=[A-Z])",
                "_",
                re.sub(r"[^A-Za-z0-9]+", "_", key).strip("_"),
            )
            if _SENSITIVE_KEY.search(normalized):
                result[key] = "[redacted]"
            else:
                result[key] = sanitize_fields(nested, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple, set, frozenset)):
        return [sanitize_fields(item, depth=depth + 1) for item in list(value)[:500]]
    return str(value)[:2_000]


def current_context() -> dict[str, Any]:
    """Return a copy of the active request/worker trace context."""

    return dict(_CONTEXT.get())


def bind_context(**fields: Any) -> Token[dict[str, Any]]:
    """Merge safe fields into the current context and return a reset token."""

    merged = current_context()
    for key, value in fields.items():
        if value is not None:
            merged[str(key)[:80]] = sanitize_fields(value)
    return _CONTEXT.set(merged)


def enrich_context(**fields: Any) -> None:
    """Add context for the remainder of the current request or worker task."""

    merged = current_context()
    for key, value in fields.items():
        if value is not None:
            merged[str(key)[:80]] = sanitize_fields(value)
    _CONTEXT.set(merged)


def reset_context(token: Token[dict[str, Any]]) -> None:
    _CONTEXT.reset(token)


class JsonLogFormatter(logging.Formatter):
    """Emit one stable JSON object per record for Log Analytics ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", None) or record.getMessage(),
        }
        payload.update(current_context())
        structured = getattr(record, "structured_fields", None)
        if isinstance(structured, Mapping):
            payload.update(sanitize_fields(structured))
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_KEYS or key in {
                "event",
                "structured_fields",
            }:
                continue
            if key.startswith("_"):
                continue
            payload[key] = sanitize_fields(value)
        if record.exc_info:
            exception = record.exc_info[1]
            payload["exception_type"] = (
                exception.__class__.__name__ if exception is not None else "Exception"
            )
        return json.dumps(
            sanitize_fields(payload),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger without embedding provider dependencies."""

    if name.startswith("app."):
        return logging.getLogger(name)
    return logging.getLogger(f"app.{name}")


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    **fields: Any,
) -> None:
    """Log a structured event after recursively removing sensitive values."""

    logger.log(
        level,
        event,
        extra={
            "event": safe_identifier(event, fallback="application.event"),
            "structured_fields": sanitize_fields(fields),
        },
    )


def configure_observability(config: Any) -> dict[str, Any]:
    """Configure JSON logs and, when available, the Azure Monitor OTel exporter.

    Missing optional Azure packages never prevent the API from starting. The
    return value is deliberately safe to log and contains no connection string.
    """

    global _CONFIGURED
    root = logging.getLogger()
    level_name = str(getattr(config, "log_level", "INFO") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    if not _CONFIGURED:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLogFormatter())
        root.handlers.clear()
        root.addHandler(handler)
        _CONFIGURED = True
    root.setLevel(level)

    requested = str(
        getattr(config, "observability_exporter", "console") or "console"
    ).strip().lower()
    connection_string = getattr(
        config, "applicationinsights_connection_string", None
    )
    azure_configured = False
    reason: str | None = None
    if requested == "azure_monitor":
        if not connection_string:
            reason = "connection_string_not_configured"
        else:
            try:
                from azure.monitor.opentelemetry import configure_azure_monitor

                configure_azure_monitor(connection_string=connection_string)
                azure_configured = True
            except (ImportError, RuntimeError, ValueError):
                reason = "azure_monitor_exporter_unavailable"
    return {
        "exporter": requested,
        "structured_logging": requested != "none",
        "azure_monitor_configured": azure_configured,
        "fallback_reason": reason,
    }


__all__ = [
    "JsonLogFormatter",
    "bind_context",
    "configure_observability",
    "current_context",
    "enrich_context",
    "get_logger",
    "log_event",
    "reset_context",
    "safe_identifier",
    "sanitize_fields",
]
