from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    transport: Literal["mqtt", "rest", "lorawan", "modbus_gateway", "ble_sync"] = "mqtt"
    hardware_model: str | None = Field(default=None, max_length=120)
    capabilities: list[str] = Field(default_factory=list, max_length=60)
    channels: list[ChannelDefinition] = Field(default_factory=list, max_length=80)
    allow_remote_control: bool = False


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


class TelemetryEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_id: str = Field(min_length=1, max_length=100)
    timestamp: datetime
    measurements: dict[str, MeasurementValue | float | int | bool | str] = Field(min_length=1, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("measurements")
    @classmethod
    def validate_keys(cls, value):
        import re
        if any(not re.fullmatch(r"[a-z][a-z0-9_]{0,99}", key) for key in value):
            raise ValueError("measurement keys must be lowercase snake_case")
        return value


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
