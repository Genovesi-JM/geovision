"""Azure IoT Hub telemetry delivered through Azure Event Grid.

Azure message and webhook details end here. The returned envelope is the
provider-neutral GeoVision protocol and is validated by the normal ingestion
service used by REST, MQTT, FieldBox, and simulators.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
import hmac
import json
from typing import Any, Mapping, Sequence

from app.core.config import Settings
from app.modules.monitoring.iot_ports import CloudTelemetryBatch, CloudTelemetryEvent


DEVICE_TELEMETRY_TYPE = "Microsoft.Devices.DeviceTelemetry"
SUBSCRIPTION_VALIDATION_TYPE = "Microsoft.EventGrid.SubscriptionValidationEvent"
MAX_EVENTS_PER_DELIVERY = 100
MAX_ENVELOPE_BYTES = 256 * 1024


class AzureIotHubPayloadError(ValueError):
    """Safe validation failure for an untrusted Event Grid delivery."""


def _events(payload: object) -> Sequence[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        values: Sequence[Mapping[str, Any]] = (payload,)
    elif isinstance(payload, list) and payload and all(
        isinstance(item, Mapping) for item in payload
    ):
        values = payload
    else:
        raise AzureIotHubPayloadError("Event Grid payload must contain events")
    if len(values) > MAX_EVENTS_PER_DELIVERY:
        raise AzureIotHubPayloadError("Event Grid delivery is too large")
    return values


def _event_type(event: Mapping[str, Any]) -> str:
    return str(event.get("eventType") or event.get("type") or "")


def _occurred_at(event: Mapping[str, Any]) -> datetime:
    raw = str(event.get("eventTime") or event.get("time") or "")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AzureIotHubPayloadError("Event Grid event time is invalid") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _json_body(data: Mapping[str, Any], system: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = data.get("body")
    if isinstance(raw, Mapping):
        encoded = json.dumps(raw, separators=(",", ":"), ensure_ascii=False).encode()
        body: object = raw
    elif isinstance(raw, str):
        content_type = str(system.get("iothub-content-type") or "").lower()
        try:
            if "json" in content_type:
                encoded = raw.encode("utf-8")
            else:
                encoded = base64.b64decode(raw, validate=True)
            body = json.loads(encoded.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error) as exc:
            raise AzureIotHubPayloadError("IoT Hub telemetry body is not valid JSON") from exc
    else:
        raise AzureIotHubPayloadError("IoT Hub telemetry body is missing")
    if len(encoded) > MAX_ENVELOPE_BYTES or not isinstance(body, Mapping):
        raise AzureIotHubPayloadError("IoT Hub telemetry envelope is invalid or too large")
    return body


class AzureIotHubEventGridAdapter:
    provider_name = "azure_iot_hub"

    def __init__(self, config: Settings):
        self.config = config

    def _authorize(self, headers: Mapping[str, str]) -> None:
        if not self.config.azure_iot_hub_enabled:
            raise AzureIotHubPayloadError("Azure IoT Hub ingestion is disabled")
        expected = self.config.azure_iot_hub_webhook_secret or ""
        supplied = headers.get("x-geovision-iot-hub-secret", "")
        if not expected or not hmac.compare_digest(expected, supplied):
            raise AzureIotHubPayloadError("Azure IoT Hub delivery is not authorized")

    def _validate_hub(self, event: Mapping[str, Any]) -> None:
        expected = (self.config.azure_iot_hub_name or "").lower()
        if not expected:
            return
        topic = str(event.get("topic") or event.get("source") or "")
        actual = topic.rstrip("/").rsplit("/", 1)[-1].lower()
        if actual != expected:
            raise AzureIotHubPayloadError("Event Grid source is not the configured IoT Hub")

    def parse_delivery(
        self,
        payload: object,
        *,
        headers: Mapping[str, str],
    ) -> CloudTelemetryBatch:
        normalized_headers = {str(key).lower(): str(value) for key, value in headers.items()}
        self._authorize(normalized_headers)
        events = _events(payload)
        if len(events) == 1 and _event_type(events[0]) == SUBSCRIPTION_VALIDATION_TYPE:
            data = events[0].get("data")
            code = str(data.get("validationCode") or "") if isinstance(data, Mapping) else ""
            if not code:
                raise AzureIotHubPayloadError("Event Grid validation code is missing")
            self._validate_hub(events[0])
            return CloudTelemetryBatch(validation_code=code, events=())

        normalized: list[CloudTelemetryEvent] = []
        for event in events:
            if _event_type(event) != DEVICE_TELEMETRY_TYPE:
                continue
            self._validate_hub(event)
            event_id = str(event.get("id") or "").strip()
            data = event.get("data")
            if not event_id or not isinstance(data, Mapping):
                raise AzureIotHubPayloadError("IoT Hub event identity or data is missing")
            system = data.get("systemProperties")
            if not isinstance(system, Mapping):
                raise AzureIotHubPayloadError("IoT Hub system properties are missing")
            provider_device_id = str(
                system.get("iothub-connection-device-id") or ""
            ).strip()
            if not provider_device_id:
                raise AzureIotHubPayloadError("IoT Hub device identity is missing")
            subject = str(event.get("subject") or "")
            if subject and subject.rstrip("/").rsplit("/", 1)[-1] != provider_device_id:
                raise AzureIotHubPayloadError("IoT Hub subject and device identity disagree")
            normalized.append(
                CloudTelemetryEvent(
                    provider_code=self.provider_name,
                    provider_event_id=event_id[:200],
                    provider_device_id=provider_device_id[:160],
                    occurred_at=_occurred_at(event),
                    envelope=dict(_json_body(data, system)),
                )
            )
        if not normalized:
            raise AzureIotHubPayloadError(
                "Event Grid delivery contains no supported IoT Hub telemetry"
            )
        return CloudTelemetryBatch(validation_code=None, events=tuple(normalized))


__all__ = [
    "AzureIotHubEventGridAdapter",
    "AzureIotHubPayloadError",
    "DEVICE_TELEMETRY_TYPE",
    "SUBSCRIPTION_VALIDATION_TYPE",
]
