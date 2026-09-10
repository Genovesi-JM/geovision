"""Project linked IoT telemetry into GeoVision's shared intelligence model.

The IoT tables remain the source of truth for raw receipts, readings, and
alerts.  This module creates the customer-facing, provider-neutral projection
used by the rest of GeoVision: technical KPIs for numeric sensor values and an
observation/action pair for each newly triggered alert.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import re
from typing import Any, Mapping, Sequence

from sqlalchemy.orm import Session

from app.models import Asset, IotAlert, IotDevice, SensorChannel, TelemetryReceipt
from app.modules.actions.services import create_action_from_recommendation
from app.modules.analytics.domain import (
    ActionRecommendation,
    KpiCalculation,
    KpiDefinitionSpec,
    KpiImportance,
    KpiStatus,
    ObservationProposal,
    ObservationSeverity,
    ValidationStatus,
)
from app.modules.analytics.services import record_kpi_value, record_observation


BRIDGE_VERSION = "1.0.0"
_LOCATION_CHANNELS = frozenset({"latitude", "longitude"})
_ACTIVE_ALERT_STATUSES = (
    "triggered",
    "notified",
    "acknowledged",
    "assigned",
)
_SEVERITY_ORDER = {"info": 0, "watch": 1, "warning": 2, "critical": 3}


@dataclass(frozen=True, slots=True)
class IotIntelligenceResult:
    """Identifiers created by one telemetry receipt's projection."""

    materialized: bool
    kpi_value_ids: tuple[str, ...] = ()
    observation_ids: tuple[str, ...] = ()
    action_ids: tuple[str, ...] = ()
    reason: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "materialized": self.materialized,
            "kpi_value_ids": list(self.kpi_value_ids),
            "observation_ids": list(self.observation_ids),
            "action_ids": list(self.action_ids),
            "reason": self.reason,
        }


def _status_for_reading(
    reading: Mapping[str, Any],
    alert_events: Sequence[Mapping[str, Any]],
    active_alert_severity: str | None = None,
) -> KpiStatus:
    severities = [
        str(event.get("severity") or "").strip().lower()
        for event in alert_events
        if event.get("type") == "alert.triggered"
        and event.get("channel") == reading.get("channel")
    ]
    if active_alert_severity:
        severities.append(active_alert_severity.strip().lower())
    worst = max(
        severities,
        key=lambda item: _SEVERITY_ORDER.get(item, -1),
        default="",
    )
    if worst == "critical":
        return KpiStatus.CRITICAL
    if worst == "warning":
        return KpiStatus.WARNING
    if worst == "watch":
        return KpiStatus.WATCH
    quality = str(reading.get("quality") or "good").strip().lower()
    if quality in {"bad", "sensor_error"}:
        return KpiStatus.WARNING
    if quality == "uncertain":
        return KpiStatus.WATCH
    return KpiStatus.GOOD


def _definition_key(device: IotDevice, channel: SensorChannel) -> str:
    """Return a stable key for one device/channel measurement stream."""

    safe_channel = re.sub(r"[^A-Za-z0-9_]+", "_", channel.key).strip("_")
    safe_channel = (safe_channel or "sensor")[:78]
    semantic = f"{device.id}\0{channel.measurement_type}\0{channel.unit or ''}"
    suffix = hashlib.sha256(semantic.encode("utf-8")).hexdigest()[:12]
    return f"iot.{safe_channel}.{suffix}"


def _observation_severity(value: object) -> ObservationSeverity:
    normalized = str(value or "warning").strip().upper()
    aliases = {"LOW": "INFO", "MEDIUM": "WATCH", "HIGH": "WARNING"}
    normalized = aliases.get(normalized, normalized)
    try:
        return ObservationSeverity(normalized)
    except ValueError:
        return ObservationSeverity.WARNING


def _action_priority(value: object) -> str:
    normalized = str(value or "warning").strip().upper()
    return {
        "INFO": "LOW",
        "LOW": "LOW",
        "WATCH": "MEDIUM",
        "MEDIUM": "MEDIUM",
        "WARNING": "HIGH",
        "HIGH": "HIGH",
        "CRITICAL": "CRITICAL",
        "URGENT": "URGENT",
    }.get(normalized, "HIGH")


def materialize_iot_intelligence(
    db: Session,
    *,
    device: IotDevice,
    receipt: TelemetryReceipt,
    readings: Sequence[Mapping[str, Any]],
    alert_events: Sequence[Mapping[str, Any]],
    measured_at: datetime,
) -> IotIntelligenceResult:
    """Create customer intelligence for a linked, in-order IoT receipt.

    Devices without a valid canonical asset/workspace remain fully usable in
    the IoT console, but cannot be projected into customer workspace data.  A
    caller must also skip this function for out-of-order replay so old edge
    data cannot overwrite the customer's current decision state.
    """

    # A receipt snapshots the assignment at ingestion time. Use it instead of
    # the device's mutable current assignment so a delayed repair cannot write
    # historical telemetry into a newly assigned workspace.
    asset = db.get(Asset, receipt.core_asset_id) if receipt.core_asset_id else None
    if asset is None or asset.organization_id != device.company_id:
        return IotIntelligenceResult(False, reason="canonical_asset_unavailable")
    if not asset.workspace_id:
        return IotIntelligenceResult(False, reason="workspace_unavailable")

    reading_channels = {
        str(reading.get("channel") or "").strip() for reading in readings
    }
    channels = {
        row.key: row
        for row in db.query(SensorChannel)
        .filter(
            SensorChannel.device_id == device.id,
            SensorChannel.key.in_(reading_channels),
        )
        .all()
    }
    active_severity: dict[str, str] = {}
    for alert in (
        db.query(IotAlert)
        .filter(
            IotAlert.company_id == device.company_id,
            IotAlert.device_id == device.id,
            IotAlert.channel.in_(reading_channels),
            IotAlert.status.in_(_ACTIVE_ALERT_STATUSES),
        )
        .all()
    ):
        current = active_severity.get(alert.channel)
        if current is None or _SEVERITY_ORDER.get(
            alert.severity.lower(), -1
        ) > _SEVERITY_ORDER.get(current, -1):
            active_severity[alert.channel] = alert.severity.lower()

    provenance = {
        "kind": "iot_telemetry",
        "device_id": device.id,
        "device_uid": device.public_id,
        "provider_code": device.provider_code,
        "receipt_id": receipt.id,
        "message_id": receipt.message_id,
        "protocol_version": receipt.protocol_version,
    }
    kpi_ids: list[str] = []
    for reading in readings:
        channel = str(reading.get("channel") or "").strip()
        value = reading.get("value")
        if (
            not channel
            or channel in _LOCATION_CHANNELS
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
        ):
            continue
        channel_definition = channels.get(channel)
        if channel_definition is None:
            continue
        definition = KpiDefinitionSpec(
            sector=asset.sector,
            key=_definition_key(device, channel_definition),
            name=channel_definition.label,
            calculator="iot.telemetry_projection",
            version=BRIDGE_VERSION,
            unit=channel_definition.unit,
            importance=KpiImportance.TECHNICAL,
            display_format={"maximum_fraction_digits": 2},
            description="Latest value received from a linked field device.",
        )
        calculation = KpiCalculation(
            value=float(value),
            measured_at=measured_at,
            source=f"iot.telemetry:{device.id}:{receipt.id}",
            confidence=(
                1.0
                if str(reading.get("quality") or "good").strip().lower() == "good"
                else 0.75
            ),
            provenance={**provenance, "channel": channel},
            status=_status_for_reading(
                reading,
                alert_events,
                active_severity.get(channel),
            ),
        )
        kpi_ids.append(
            record_kpi_value(
                db,
                asset=asset,
                definition=definition,
                calculation=calculation,
                workspace_id=asset.workspace_id,
            ).id
        )

    observation_ids: list[str] = []
    action_ids: list[str] = []
    for event in alert_events:
        if event.get("type") != "alert.triggered" or not event.get("id"):
            continue
        alert_id = str(event["id"])
        channel = str(event.get("channel") or "sensor")
        severity = _observation_severity(event.get("severity"))
        observation = record_observation(
            db,
            asset=asset,
            workspace_id=asset.workspace_id,
            proposal=ObservationProposal(
                key=f"iot_alert:{alert_id}",
                observation_type="IOT_SENSOR_ALERT",
                severity=severity,
                detected_at=measured_at,
                source="iot.telemetry",
                algorithm_key="iot.alert_rule",
                algorithm_version=BRIDGE_VERSION,
                confidence=1.0,
                value={
                    "alert_id": alert_id,
                    "channel": channel,
                    "message": str(event.get("message") or "Field sensor alert"),
                },
                numeric_value=(
                    float(event["value"])
                    if isinstance(event.get("value"), (int, float))
                    and not isinstance(event.get("value"), bool)
                    else None
                ),
                unit=str(event.get("unit")) if event.get("unit") else None,
                metadata={"device_name": device.name},
                provenance=provenance,
                validation_status=ValidationStatus.NEEDS_REVIEW,
            ),
        )
        observation_ids.append(observation.id)
        recommendation = ActionRecommendation(
            key=f"inspect_iot_alert:{alert_id}",
            priority=_action_priority(event.get("severity")),
            title=f"Review {channel.replace('_', ' ')} alert",
            description=(
                f"Inspect {device.name} and its linked asset. "
                f"The device reported: {event.get('message') or 'a sensor alert'}."
            ),
            source_observation_key=f"iot_alert:{alert_id}",
            recommendation_refs=(
                {
                    "kind": "iot_alert",
                    "alert_id": alert_id,
                    "device_id": device.id,
                    "receipt_id": receipt.id,
                },
            ),
        )
        action, _ = create_action_from_recommendation(
            db,
            asset=asset,
            rule_key="iot.alert_rule",
            rule_version=BRIDGE_VERSION,
            recommendation=recommendation,
            source_observation_id=observation.id,
        )
        action_ids.append(action.id)

    return IotIntelligenceResult(
        True,
        kpi_value_ids=tuple(kpi_ids),
        observation_ids=tuple(observation_ids),
        action_ids=tuple(action_ids),
    )


__all__ = ["BRIDGE_VERSION", "IotIntelligenceResult", "materialize_iot_intelligence"]
