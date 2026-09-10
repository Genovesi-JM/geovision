"""Normalize Azure Event Grid storage events into provider-neutral objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hmac
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence
from urllib.parse import unquote, urlsplit

from app.core.config import Settings


BLOB_CREATED_TYPE = "Microsoft.Storage.BlobCreated"
SUBSCRIPTION_VALIDATION_TYPE = "Microsoft.EventGrid.SubscriptionValidationEvent"


class EventGridPayloadError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BlobCreatedNotification:
    event_id: str
    occurred_at: datetime
    container: str
    object_key: str
    size_bytes: int
    content_type: str | None
    etag: str | None


@dataclass(frozen=True, slots=True)
class EventGridBatch:
    validation_code: str | None
    notifications: tuple[BlobCreatedNotification, ...]


def _event_type(event: Mapping[str, Any]) -> str:
    return str(event.get("eventType") or event.get("type") or "")


def _event_time(event: Mapping[str, Any]) -> datetime:
    raw = str(event.get("eventTime") or event.get("time") or "")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EventGridPayloadError("Event Grid time is invalid") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _events(payload: object) -> Sequence[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        return (payload,)
    if not isinstance(payload, list) or not payload:
        raise EventGridPayloadError("Event Grid payload must contain at least one event")
    if not all(isinstance(item, Mapping) for item in payload):
        raise EventGridPayloadError("Every Event Grid item must be an object")
    return payload


def _authorize(headers: Mapping[str, str], config: Settings) -> None:
    if not config.azure_event_grid_enabled:
        raise EventGridPayloadError("Event Grid ingestion is disabled")
    expected_secret = config.azure_event_grid_webhook_secret or ""
    supplied_secret = headers.get("x-geovision-event-grid-secret", "")
    if expected_secret and not hmac.compare_digest(expected_secret, supplied_secret):
        raise EventGridPayloadError("Event Grid delivery is not authorized")
    expected_subscription = config.azure_event_grid_subscription_name
    supplied_subscription = headers.get("aeg-subscription-name")
    if expected_subscription and supplied_subscription != expected_subscription:
        raise EventGridPayloadError("Event Grid subscription is not authorized")


def _blob_notification(
    event: Mapping[str, Any],
    config: Settings,
) -> BlobCreatedNotification:
    event_id = str(event.get("id") or "").strip()
    data = event.get("data")
    if not event_id or not isinstance(data, Mapping):
        raise EventGridPayloadError("BlobCreated event identity or data is missing")
    raw_url = str(data.get("url") or "")
    parsed = urlsplit(raw_url)
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.query or parsed.fragment:
        raise EventGridPayloadError("BlobCreated URL is invalid")
    if config.azure_storage_account_url:
        expected_host = urlsplit(config.azure_storage_account_url).hostname
        if expected_host and parsed.hostname.lower() != expected_host.lower():
            raise EventGridPayloadError("BlobCreated storage account does not match GeoVision")
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise EventGridPayloadError("BlobCreated URL has no object key")
    container, key_parts = parts[0], parts[1:]
    if container != config.azure_storage_container:
        raise EventGridPayloadError("BlobCreated container does not match GeoVision")
    if any(part in {".", ".."} or "\x00" in part for part in key_parts):
        raise EventGridPayloadError("BlobCreated object key is unsafe")
    object_key = str(PurePosixPath(*key_parts))
    try:
        size = int(data.get("contentLength") or 0)
    except (TypeError, ValueError) as exc:
        raise EventGridPayloadError("BlobCreated content length is invalid") from exc
    if size < 0:
        raise EventGridPayloadError("BlobCreated content length is invalid")
    return BlobCreatedNotification(
        event_id=event_id[:200],
        occurred_at=_event_time(event),
        container=container,
        object_key=object_key,
        size_bytes=size,
        content_type=(str(data["contentType"])[:150] if data.get("contentType") else None),
        etag=(str(data["eTag"])[:200] if data.get("eTag") else None),
    )


def parse_event_grid_batch(
    payload: object,
    *,
    headers: Mapping[str, str],
    config: Settings,
) -> EventGridBatch:
    """Authenticate and normalize Event Grid and CloudEvents v1 deliveries."""

    normalized_headers = {str(key).lower(): str(value) for key, value in headers.items()}
    _authorize(normalized_headers, config)
    events = _events(payload)
    if len(events) == 1 and _event_type(events[0]) == SUBSCRIPTION_VALIDATION_TYPE:
        data = events[0].get("data")
        code = str(data.get("validationCode") or "") if isinstance(data, Mapping) else ""
        if not code:
            raise EventGridPayloadError("Event Grid validation code is missing")
        return EventGridBatch(validation_code=code, notifications=())
    notifications: list[BlobCreatedNotification] = []
    for event in events:
        if _event_type(event) != BLOB_CREATED_TYPE:
            continue
        notifications.append(_blob_notification(event, config))
    if not notifications:
        raise EventGridPayloadError("Event Grid batch contains no supported BlobCreated events")
    return EventGridBatch(validation_code=None, notifications=tuple(notifications))


__all__ = [
    "BLOB_CREATED_TYPE",
    "BlobCreatedNotification",
    "EventGridBatch",
    "EventGridPayloadError",
    "SUBSCRIPTION_VALIDATION_TYPE",
    "parse_event_grid_batch",
]
