from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


TELEMETRY_PROTOCOL_VERSION = "geovision.telemetry.v1"
_SENSITIVE_KEY = re.compile(
    r"(^|_)(password|passwd|secret|token|api_key|authorization|credential|private_key)($|_)",
    re.IGNORECASE,
)


def _validate_context(value: Any, *, path: str) -> Any:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(key)).strip("_")
            if _SENSITIVE_KEY.search(normalized):
                raise ValueError(f"{path} must not contain credentials or secrets")
            _validate_context(nested, path=f"{path}.{key}")
    elif isinstance(value, list):
        for nested in value:
            _validate_context(nested, path=path)
    try:
        encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} must be JSON-compatible") from exc
    if len(encoded.encode("utf-8")) > 65_536:
        raise ValueError(f"{path} must not exceed 64 KiB")
    return value


class ChannelDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    label: str = Field(min_length=1, max_length=160)
    measurement_type: str = Field(min_length=1, max_length=80)
    unit: str | None = Field(default=None, max_length=30)
    data_type: Literal["number", "boolean", "text"] = "number"
    minimum: float | None = None
    maximum: float | None = None
    precision: int = Field(default=2, ge=0, le=8)


class DeviceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=160)
    site_id: str
    asset_id: str | None = None
    gateway_id: str | None = None
    device_type: str = Field(default="multi_sensor", min_length=2, max_length=60)
    transport: Literal[
        "mqtt", "rest", "lorawan", "modbus_gateway", "ble_sync", "azure_iot_hub"
    ] = "mqtt"
    provider_code: Literal["geovision", "fieldbox", "azure_iot_hub"] = "geovision"
    provider_device_id: str | None = Field(default=None, min_length=1, max_length=160)
    protocol_version: Literal[TELEMETRY_PROTOCOL_VERSION] = TELEMETRY_PROTOCOL_VERSION
    hardware_model: str | None = Field(default=None, max_length=120)
    capabilities: list[str] = Field(default_factory=list, max_length=60)
    channels: list[ChannelDefinition] = Field(default_factory=list, max_length=80)
    allow_remote_control: bool = False

    @model_validator(mode="after")
    def validate_provider_identity(self):
        if self.provider_code == "azure_iot_hub" and not self.provider_device_id:
            raise ValueError("provider_device_id is required for Azure IoT Hub devices")
        if self.transport == "azure_iot_hub" and self.provider_code != "azure_iot_hub":
            raise ValueError("azure_iot_hub transport requires the Azure IoT Hub provider")
        return self


class ProvisionExchange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_uid: str = Field(min_length=3, max_length=80)
    provisioning_token: str = Field(min_length=20, max_length=300)
    firmware_version: str | None = Field(default=None, max_length=80)


class MeasurementValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Any
    unit: str | None = Field(default=None, max_length=30)
    quality: Literal["good", "uncertain", "bad", "sensor_error"] = "good"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value):
        return _validate_context(value, path="measurement metadata")


class TelemetryLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_meters: float | None = Field(default=None, ge=0, le=100_000)


class TelemetryEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: Literal[TELEMETRY_PROTOCOL_VERSION] = TELEMETRY_PROTOCOL_VERSION
    device_id: str | None = Field(default=None, min_length=1, max_length=160)
    message_id: str = Field(min_length=1, max_length=100)
    timestamp: datetime
    stream_id: str | None = Field(
        default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$"
    )
    sequence: int | None = Field(default=None, ge=0)
    firmware_version: str | None = Field(default=None, min_length=1, max_length=80)
    replayed_from_edge: bool = False
    queued_at: datetime | None = None
    location: TelemetryLocation | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    measurements: dict[str, MeasurementValue | float | int | bool | str] = Field(min_length=1, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("measurements")
    @classmethod
    def validate_keys(cls, value):
        if any(not re.fullmatch(r"[a-z][a-z0-9_]{0,99}", key) for key in value):
            raise ValueError("measurement keys must be lowercase snake_case")
        return value

    @field_validator("context", "metadata")
    @classmethod
    def validate_context_fields(cls, value, info):
        return _validate_context(value, path=info.field_name)

    @model_validator(mode="after")
    def validate_delivery_contract(self):
        if (self.stream_id is None) != (self.sequence is None):
            raise ValueError("stream_id and sequence must be supplied together")
        if self.replayed_from_edge and (self.stream_id is None or self.queued_at is None):
            raise ValueError(
                "store-and-forward telemetry requires stream_id, sequence, and queued_at"
            )
        return self


class MqttEnvelope(TelemetryEnvelope):
    device_uid: str = Field(min_length=3, max_length=80)
    nonce: str = Field(min_length=8, max_length=100)
    signature: str = Field(min_length=64, max_length=64)


class AlertRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=160)
    device_id: str | None = None
    site_id: str | None = None
    channel: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    operator: Literal["gt", "gte", "lt", "lte", "eq", "ne", "rapid_rise", "rapid_fall"]
    threshold: float
    severity: Literal["info", "warning", "critical"] = "warning"
    cooldown_seconds: int = Field(default=300, ge=0, le=86400)
    sustained_seconds: int = Field(default=0, ge=0, le=86400)
    notification_channels: list[Literal["log", "email", "telegram", "push", "sms", "whatsapp"]] = ["log"]


class AlertAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assignee_id: str = Field(min_length=1, max_length=80)


class DeviceAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str = Field(min_length=1, max_length=36)
    reason: str = Field(min_length=4, max_length=500)


class CommandCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal[
        "beacon_on", "beacon_off", "buzzer_on", "buzzer_off",
        "demo_fan_on", "demo_fan_off", "low_voltage_valve_open",
        "low_voltage_valve_close", "relay_on", "relay_off",
        "set_reporting_interval", "restart", "request_diagnostics",
    ]
    arguments: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool
    reason: str = Field(min_length=4, max_length=500)
    fail_safe_state: str = Field(default="off", min_length=2, max_length=100)


class CommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str
    status: Literal["acknowledged", "completed", "failed", "rejected", "timed_out"]
    actual_state: dict[str, Any] = Field(default_factory=dict)
    message: str | None = Field(default=None, max_length=500)


class CommissioningCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checklist: dict[str, bool]
    result: Literal["passed", "failed", "conditional"]
    notes: str | None = Field(default=None, max_length=2000)


class CalibrationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offset: float = 0
    scale: float = 1
    reference_value: float | None = None
    measured_value: float | None = None
    notes: str | None = Field(default=None, max_length=2000)
