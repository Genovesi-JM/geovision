"""Strict transport contracts for the integration connection registry."""

from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.integration import sanitize_integration_message

from .domain import (
    ConnectionHealth,
    ProviderFamily,
    SyncDirection,
    SyncOutcome,
    SyncTrigger,
    normalize_identifier,
    reject_secret_like_settings,
    validate_capabilities,
    validate_provider,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        hide_input_in_errors=True,
        use_enum_values=True,
    )


_VAULT_HOST = re.compile(
    r"^(?=.{3,24}\.vault\.azure\.net$)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.vault\.azure\.net$"
)
_VAULT_SECRET_NAME = re.compile(r"^[A-Za-z0-9-]{1,127}$")
_VAULT_SECRET_VERSION = re.compile(r"^[A-Za-z0-9-]{1,128}$")
_SECRET_TEXT = re.compile(
    r"(?i)(?:bearer\s+\S+|(?:authorization|credential|password|secret|token|"
    r"api[_ -]?key|private[_ -]?key|client[_ -]?secret)\s*[:=]\s*\S+)"
)


def _https_endpoint(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    parsed = urlsplit(normalized)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "endpoint_url must be an HTTPS origin/path without credentials, query, or fragment"
        )
    return normalized


def _reference(value: str | None, *, field: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > 500:
        raise ValueError(f"{field} must be a bounded opaque reference")
    if any(character.isspace() for character in normalized):
        raise ValueError(f"{field} must not contain whitespace")
    return normalized


def _configuration_metadata(value: str | None, *, field: str) -> str | None:
    normalized = _reference(value, field=field)
    if normalized is None:
        return None
    parsed = urlsplit(normalized)
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or _SECRET_TEXT.search(normalized)
    ):
        raise ValueError(f"{field} must not contain secret material")
    return normalized


def _secret_reference(value: str | None, *, field: str) -> str | None:
    normalized = _reference(value, field=field)
    if normalized is None:
        return None
    parsed = urlsplit(normalized)
    host = parsed.hostname
    segments = parsed.path.split("/")
    azure_https = (
        parsed.scheme == "https"
        and host is not None
        and parsed.netloc == host
        and _VAULT_HOST.fullmatch(host) is not None
        and len(segments) in {3, 4}
        and segments[0] == ""
        and segments[1] == "secrets"
        and _VAULT_SECRET_NAME.fullmatch(segments[2]) is not None
        and (
            len(segments) == 3
            or _VAULT_SECRET_VERSION.fullmatch(segments[3]) is not None
        )
        and "%" not in parsed.path
    )
    if (
        not azure_https
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            f"{field} must be a canonical Azure Key Vault HTTPS secret reference"
        )
    return normalized


class IntegrationConnectionCreate(_StrictModel):
    workspace_id: str | None = Field(default=None, min_length=1, max_length=36)
    member_user_id: str | None = Field(default=None, min_length=1, max_length=36)
    connection_key: str = Field(min_length=2, max_length=100)
    provider_family: ProviderFamily
    provider_code: str = Field(min_length=2, max_length=100)
    display_name: str = Field(min_length=2, max_length=160)
    endpoint_url: str | None = Field(default=None, max_length=500)
    configuration_reference: str | None = Field(default=None, max_length=500)
    settings: dict[str, Any] = Field(default_factory=dict)
    credential_reference: str | None = Field(default=None, max_length=500)
    webhook_secret_reference: str | None = Field(default=None, max_length=500)
    capabilities: list[str] = Field(min_length=1, max_length=20)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    retry_max_attempts: int = Field(default=3, ge=1, le=10)
    retry_base_seconds: int = Field(default=2, ge=1, le=300)
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=60_000)
    circuit_failure_threshold: int = Field(default=5, ge=1, le=100)

    @field_validator("connection_key")
    @classmethod
    def stable_key(cls, value: str) -> str:
        return normalize_identifier(value, field="connection_key")

    @field_validator("display_name")
    @classmethod
    def visible_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("display_name is too short")
        return normalized

    @field_validator("endpoint_url")
    @classmethod
    def secure_endpoint(cls, value: str | None) -> str | None:
        return _https_endpoint(value)

    @field_validator(
        "configuration_reference",
        "credential_reference",
        "webhook_secret_reference",
    )
    @classmethod
    def bounded_reference(cls, value: str | None, info) -> str | None:
        if info.field_name in {"credential_reference", "webhook_secret_reference"}:
            return _secret_reference(value, field=info.field_name)
        return _configuration_metadata(value, field=info.field_name)

    @field_validator("settings")
    @classmethod
    def safe_settings(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_secret_like_settings(value)
        encoded = json.dumps(value, ensure_ascii=False, default=str)
        if len(encoded.encode("utf-8")) > 16 * 1024:
            raise ValueError("settings exceeds the 16 KiB limit")
        return value

    @model_validator(mode="after")
    def registered_provider_and_capabilities(self):
        self.provider_code = validate_provider(self.provider_family, self.provider_code)
        self.capabilities = validate_capabilities(
            self.provider_family, self.capabilities
        )
        return self


class IntegrationConnectionUpdate(_StrictModel):
    expected_version: int = Field(ge=1)
    display_name: str | None = Field(default=None, min_length=2, max_length=160)
    endpoint_url: str | None = Field(default=None, max_length=500)
    configuration_reference: str | None = Field(default=None, max_length=500)
    settings: dict[str, Any] | None = None
    credential_reference: str | None = Field(default=None, max_length=500)
    webhook_secret_reference: str | None = Field(default=None, max_length=500)
    capabilities: list[str] | None = Field(default=None, min_length=1, max_length=20)
    timeout_seconds: int | None = Field(default=None, ge=1, le=300)
    retry_max_attempts: int | None = Field(default=None, ge=1, le=10)
    retry_base_seconds: int | None = Field(default=None, ge=1, le=300)
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=60_000)
    circuit_failure_threshold: int | None = Field(default=None, ge=1, le=100)

    @field_validator("display_name")
    @classmethod
    def visible_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("display_name is too short")
        return normalized

    @field_validator("endpoint_url")
    @classmethod
    def secure_endpoint(cls, value: str | None) -> str | None:
        return _https_endpoint(value)

    @field_validator(
        "configuration_reference",
        "credential_reference",
        "webhook_secret_reference",
    )
    @classmethod
    def bounded_reference(cls, value: str | None, info) -> str | None:
        if info.field_name in {"credential_reference", "webhook_secret_reference"}:
            return _secret_reference(value, field=info.field_name)
        return _configuration_metadata(value, field=info.field_name)

    @field_validator("settings")
    @classmethod
    def safe_settings(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None:
            reject_secret_like_settings(value)
            encoded = json.dumps(value, ensure_ascii=False, default=str)
            if len(encoded.encode("utf-8")) > 16 * 1024:
                raise ValueError("settings exceeds the 16 KiB limit")
        return value


class IntegrationConnectionOut(BaseModel):
    id: str
    organization_id: str
    workspace_id: str | None
    member_user_id: str | None
    connection_key: str
    provider_family: str
    provider_code: str
    display_name: str
    status: str
    enabled: bool
    endpoint_configured: bool
    configuration_configured: bool
    credential_configured: bool
    webhook_secret_configured: bool
    capabilities: list[str]
    last_sync_started_at: datetime | None
    last_sync_succeeded_at: datetime | None
    last_sync_failed_at: datetime | None
    last_error_code: str | None
    last_error_summary: str | None
    health_status: str
    health_checked_at: datetime | None
    timeout_seconds: int
    retry_max_attempts: int
    retry_base_seconds: int
    rate_limit_per_minute: int | None
    circuit_state: str
    circuit_failure_threshold: int
    circuit_failure_count: int
    circuit_opened_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    disconnected_at: datetime | None


class ConnectionLifecycleRequest(_StrictModel):
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=300)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(sanitize_integration_message(value).split())
        return normalized or None


class IntegrationSyncRunCreate(_StrictModel):
    direction: SyncDirection
    operation: str = Field(min_length=2, max_length=100)
    trigger: SyncTrigger = SyncTrigger.MANUAL
    idempotency_key: str = Field(min_length=8, max_length=160)
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = Field(default=None, max_length=100)
    simulation_outcome: SyncOutcome | None = None
    retry_after_seconds: int | None = Field(default=None, ge=1, le=86_400)

    @field_validator("operation")
    @classmethod
    def stable_operation(cls, value: str) -> str:
        return normalize_identifier(value, field="operation")

    @field_validator("idempotency_key", "correlation_id")
    @classmethod
    def bounded_visible_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if any(ord(character) < 32 for character in normalized):
            raise ValueError("identifier contains control characters")
        return normalized

    @field_validator("payload")
    @classmethod
    def safe_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_secret_like_settings(value, path="payload")
        encoded = json.dumps(value, ensure_ascii=False, default=str)
        if len(encoded.encode("utf-8")) > 64 * 1024:
            raise ValueError("payload exceeds the 64 KiB request limit")
        return value


class IntegrationSyncRunOut(BaseModel):
    id: str
    connection_id: str
    organization_id: str
    workspace_id: str | None
    direction: str
    operation: str
    trigger: str
    status: str
    idempotency_key: str
    payload_sha256: str
    correlation_id: str | None
    attempt_count: int
    max_attempts: int
    next_retry_at: datetime | None
    failure_code: str | None
    failure_summary: str | None
    started_at: datetime | None
    completed_at: datetime | None
    requested_by_user_id: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class IntegrationSyncRetryRequest(_StrictModel):
    expected_version: int = Field(ge=1)
    simulation_outcome: SyncOutcome = SyncOutcome.SUCCESS
    retry_after_seconds: int | None = Field(default=None, ge=1, le=86_400)


class IntegrationSyncEventOut(BaseModel):
    id: str
    sync_run_id: str
    connection_id: str
    organization_id: str
    workspace_id: str | None
    direction: str
    operation: str
    resource_type: str | None
    resource_id: str | None
    external_reference: str | None
    idempotency_key: str
    payload_sha256: str
    status: str
    attempt_count: int
    next_retry_at: datetime | None
    failure_code: str | None
    failure_summary: str | None
    started_at: datetime | None
    completed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class IntegrationHealthOut(BaseModel):
    connection_id: str
    status: str
    health_status: ConnectionHealth | str
    enabled: bool
    provider_available: bool
    circuit_state: str
    checked_at: datetime
    reason_code: str | None = None


class FeatureFlagOverridePut(_StrictModel):
    workspace_id: str = Field(min_length=1, max_length=36)
    member_user_id: str | None = Field(default=None, min_length=1, max_length=36)
    enabled: bool
    expected_version: int | None = Field(default=None, ge=1)
    source: Literal[
        "admin",
        "geovision",
        "azure",
        "azure_app_configuration",
    ] = "admin"
    configuration_reference: str | None = Field(default=None, max_length=500)
    etag: str | None = Field(default=None, max_length=200)
    configuration_version: str | None = Field(default=None, max_length=120)

    @field_validator("source")
    @classmethod
    def stable_source(cls, value: str) -> str:
        return normalize_identifier(value, field="source")

    @field_validator("configuration_reference", "etag", "configuration_version")
    @classmethod
    def bounded_configuration_metadata(cls, value: str | None, info) -> str | None:
        return _configuration_metadata(value, field=info.field_name)

    @model_validator(mode="after")
    def configuration_source_contract(self):
        azure_source = self.source in {"azure", "azure_app_configuration"}
        if azure_source and not self.configuration_reference:
            raise ValueError(
                "Azure App Configuration overrides require a configuration_reference"
            )
        if not azure_source and any(
            (self.configuration_reference, self.etag, self.configuration_version)
        ):
            raise ValueError(
                "configuration metadata is only valid for Azure App Configuration overrides"
            )
        return self


class FeatureFlagOverrideOut(BaseModel):
    id: str
    organization_id: str
    workspace_id: str
    member_user_id: str | None
    flag_key: str
    enabled: bool
    source: str
    configuration_reference: str | None
    etag: str | None
    configuration_version: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class FeatureFlagResolutionOut(BaseModel):
    flag_key: str
    enabled: bool
    source: str
    scope: str
    workspace_id: str
    member_user_id: str | None


__all__ = [
    "ConnectionLifecycleRequest",
    "FeatureFlagOverrideOut",
    "FeatureFlagOverridePut",
    "FeatureFlagResolutionOut",
    "IntegrationConnectionCreate",
    "IntegrationConnectionOut",
    "IntegrationConnectionUpdate",
    "IntegrationHealthOut",
    "IntegrationSyncEventOut",
    "IntegrationSyncRetryRequest",
    "IntegrationSyncRunCreate",
    "IntegrationSyncRunOut",
]
