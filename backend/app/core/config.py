"""Typed, provider-neutral runtime configuration for GeoVision.

Every application setting is loaded here. Domain code receives providers or
safe configuration values; it must not read credentials directly from the
process environment.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import re
import secrets
import uuid
import warnings
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .passwords import validate_admin_password


_INSECURE_DEFAULT = "CHANGE_ME"
_INSECURE_MARKERS = (
    "change_me",
    "change-this",
    "change_this",
    "your-secret",
    "your_super_secret",
    "your-super-secret",
)
_PROVIDER_NAME = re.compile(r"^[a-z0-9][a-z0-9_]{0,62}$")
_MICROSOFT_GRAPH_APP_ID = "00000003-0000-0000-c000-000000000000"
_MICROSOFT_GRAPH_RESOURCE = "https://graph.microsoft.com"
_URL_FIELDS = frozenset(
    {
        "backend_base",
        "entra_external_id_discovery_url",
        "entra_external_id_issuer",
        "erpnext_base_url",
        "frontend_base",
        "multicaixa_api_url",
        "multicaixa_callback_url",
        "paypal_cancel_url",
        "paypal_return_url",
        "s3_endpoint_url",
    }
)


def _safe_origin(value: str) -> str:
    """Return an origin-only URL that cannot expose userinfo, paths, or queries."""

    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.hostname:
        return "[configured]" if value else ""
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = f":{parsed.port}" if parsed.port else ""
    except ValueError:
        port = ""
    return f"{parsed.scheme}://{host}{port}"


class RuntimeEnvironment(str, Enum):
    """Supported deployment profiles, independent of the hosting vendor."""

    LOCAL = "local"
    DEVELOPMENT = "dev"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "prod"

    def __str__(self) -> str:
        return self.value


class Settings(BaseSettings):
    """Single source of truth for environment and provider configuration."""

    app_name: str = "GeoVision Backend"
    app_version: str = "1.0.0"
    env: Optional[RuntimeEnvironment] = Field(default=None, validation_alias="ENV")
    legacy_environment: Optional[RuntimeEnvironment] = Field(
        default=None,
        validation_alias="ENVIRONMENT",
        exclude=True,
        repr=False,
    )
    port: int = Field(default=8010, ge=1, le=65535)
    migrate_timeout_seconds: int = Field(
        default=120,
        ge=1,
        validation_alias=AliasChoices("MIGRATE_TIMEOUT_SECONDS", "MIGRATE_TIMEOUT"),
    )

    # Public application URLs and browser access.
    frontend_base: str = Field(default="http://127.0.0.1:8001", repr=False)
    backend_base: str = Field(default="http://127.0.0.1:8010", repr=False)
    cors_origins: str = Field(default="", repr=False)
    trusted_proxy_cidrs: str = Field(default="", repr=False)

    # JWT/authentication. Secret fields are excluded from Settings repr/str.
    secret_key: str = Field(default=_INSECURE_DEFAULT, repr=False)
    algorithm: str = "HS256"
    access_token_expires_minutes: int = Field(default=60, ge=1)
    refresh_token_expires_days: int = Field(default=30, ge=1)
    admin_password: Optional[str] = Field(default=None, repr=False)
    admin_emails: str = Field(default="", repr=False)
    internal_token_issuer: str = "geovision"
    internal_token_audience: str = "geovision-api"
    accept_legacy_access_tokens: bool = True
    external_identity_session_max_hours: int = Field(default=24, ge=1, le=720)

    # Identity providers. Legacy Google/Microsoft browser callbacks continue to
    # mint GeoVision sessions while Entra External ID is introduced behind a
    # strict API access-token validation boundary.
    identity_provider: str = "internal"
    identity_auto_link_verified_email: bool = False
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = Field(default=None, repr=False)
    microsoft_client_id: Optional[str] = None
    microsoft_client_secret: Optional[str] = Field(default=None, repr=False)
    microsoft_tenant_id: str = "common"
    entra_external_id_issuer: Optional[str] = Field(default=None, repr=False)
    entra_external_id_audience: Optional[str] = Field(default=None, repr=False)
    entra_external_id_tenant_id: Optional[str] = Field(default=None, repr=False)
    entra_external_id_discovery_url: Optional[str] = Field(default=None, repr=False)
    entra_external_id_required_scope: Optional[str] = "access_as_user"
    entra_external_id_authorized_party: Optional[str] = Field(default=None, repr=False)
    entra_external_id_clock_skew_seconds: int = Field(default=60, ge=0, le=300)
    entra_external_id_jwks_cache_seconds: int = Field(
        default=3600,
        ge=60,
        le=86400,
    )

    # Encryption at rest for connector/provider credentials.
    encryption_key: Optional[str] = Field(default=None, repr=False)

    # Primary and compatibility databases.
    database_url: str = Field(default="sqlite:///./geovision.db", repr=False)
    accounts_database_url: str = Field(default="sqlite:///./accounts.db", repr=False)

    # AI configuration. Structured GeoVision data remains numerical truth.
    openai_api_key: Optional[str] = Field(default=None, repr=False)
    openai_model: str = "gpt-4o-mini"

    # Provider-neutral selections for capabilities implemented in later phases.
    queue_provider: str = "null"
    processing_provider: str = "none"
    weather_provider: str = "none"
    satellite_provider: str = "none"
    gis_provider: str = "none"
    construction_provider: str = "none"
    asset_management_provider: str = "none"
    maritime_provider: str = "none"

    # Shared integration timeout/retry conventions.
    integration_connect_timeout_seconds: float = Field(default=5.0, gt=0)
    integration_read_timeout_seconds: float = Field(default=30.0, gt=0)
    integration_retry_attempts: int = Field(default=3, ge=1, le=10)
    integration_retry_initial_seconds: float = Field(default=0.5, ge=0)
    integration_retry_max_seconds: float = Field(default=8.0, ge=0)

    # Object storage. The first implementation is S3-compatible, but consumers
    # depend only on ObjectStorageProvider.
    object_storage_provider: str = "s3"
    s3_bucket: Optional[str] = None
    s3_endpoint_url: Optional[str] = Field(default=None, repr=False)
    s3_region: str = "eu-west-1"
    s3_access_key_id: Optional[str] = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices("S3_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID"),
    )
    s3_secret_access_key: Optional[str] = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices("S3_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY"),
    )

    # ERP integration. GeoVision remains the system of record.
    erp_provider: str = "mock"
    erpnext_base_url: Optional[str] = Field(default=None, repr=False)
    erpnext_api_key: Optional[str] = Field(default=None, repr=False)
    erpnext_api_secret: Optional[str] = Field(default=None, repr=False)
    erpnext_webhook_secret: Optional[str] = Field(default=None, repr=False)

    # Notifications. MAIL_* aliases preserve the older deployment guide.
    notification_provider: str = "auto"
    smtp_host: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("SMTP_HOST", "MAIL_HOST"),
    )
    smtp_port: int = Field(
        default=25,
        ge=1,
        le=65535,
        validation_alias=AliasChoices("SMTP_PORT", "MAIL_PORT"),
    )
    smtp_user: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("SMTP_USER", "MAIL_USERNAME"),
    )
    smtp_password: Optional[str] = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices("SMTP_PASSWORD", "MAIL_PASSWORD"),
    )
    smtp_from: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("SMTP_FROM", "MAIL_FROM"),
    )
    smtp_use_tls: bool = True
    smtp_timeout_seconds: float = Field(default=15.0, gt=0)

    # Payments. Phase 8 owns lifecycle consolidation; these fields remove raw
    # environment access from the existing adapters today.
    multicaixa_api_url: str = Field(
        default="https://api.multicaixa.co.ao/v1",
        repr=False,
    )
    multicaixa_merchant_id: Optional[str] = None
    multicaixa_api_key: Optional[str] = Field(default=None, repr=False)
    multicaixa_webhook_secret: Optional[str] = Field(default=None, repr=False)
    multicaixa_callback_url: Optional[str] = Field(default=None, repr=False)
    stripe_secret_key: Optional[str] = Field(default=None, repr=False)
    stripe_publishable_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = Field(default=None, repr=False)
    company_iban: str = Field(default="AO06004400005506300102101", repr=False)
    company_bic: str = "BFAOAOAO"
    company_bank_name: str = "Banco de Fomento Angola"
    company_iban_intl: str = Field(default="PT50003600559910003085730", repr=False)
    company_bic_intl: str = "MPIOPTPL"
    company_bank_intl: str = "Banco Millennium BCP"
    paypal_client_id: Optional[str] = None
    paypal_secret: Optional[str] = Field(default=None, repr=False)
    paypal_mode: str = "sandbox"
    paypal_return_url: str = Field(
        default="https://geovisionops.com/loja.html?paypal=success",
        repr=False,
    )
    paypal_cancel_url: str = Field(
        default="https://geovisionops.com/loja.html?paypal=cancel",
        repr=False,
    )

    # IoT bridge. MQTT is opt-in so ordinary development needs no broker.
    mqtt_enabled: bool = False
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = Field(default=1883, ge=1, le=65535)
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = Field(default=None, repr=False)
    mqtt_tls: bool = False
    mqtt_topic_prefix: str = "geovision"
    mqtt_client_id: str = "geovision-backend"
    iot_message_max_age_seconds: int = Field(default=300, ge=1)
    iot_offline_after_seconds: int = Field(default=120, ge=1)
    iot_command_ttl_seconds: int = Field(default=300, ge=1)
    iot_max_messages_per_minute: int = Field(default=120, ge=1)
    iot_raw_retention_days: int = Field(default=30, ge=1)
    iot_aggregate_retention_days: int = Field(default=730, ge=1)

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
        hide_input_in_errors=True,
    )

    _SECRET_FIELDS = frozenset(
        {
            "secret_key",
            "admin_password",
            "admin_emails",
            "google_client_secret",
            "microsoft_client_secret",
            "entra_external_id_audience",
            "entra_external_id_tenant_id",
            "entra_external_id_authorized_party",
            "encryption_key",
            "database_url",
            "accounts_database_url",
            "openai_api_key",
            "s3_access_key_id",
            "s3_secret_access_key",
            "erpnext_api_key",
            "erpnext_api_secret",
            "erpnext_webhook_secret",
            "smtp_password",
            "multicaixa_api_key",
            "multicaixa_webhook_secret",
            "stripe_secret_key",
            "stripe_webhook_secret",
            "company_iban",
            "company_iban_intl",
            "paypal_secret",
            "mqtt_password",
        }
    )

    @field_validator("env", "legacy_environment", mode="before")
    @classmethod
    def normalize_environment(cls, value: Any) -> Optional[RuntimeEnvironment]:
        if value is None or not str(value).strip():
            return None
        if isinstance(value, RuntimeEnvironment):
            return value
        aliases = {
            "local": RuntimeEnvironment.LOCAL,
            "dev": RuntimeEnvironment.DEVELOPMENT,
            "development": RuntimeEnvironment.DEVELOPMENT,
            "test": RuntimeEnvironment.TEST,
            "testing": RuntimeEnvironment.TEST,
            "stage": RuntimeEnvironment.STAGING,
            "staging": RuntimeEnvironment.STAGING,
            "prod": RuntimeEnvironment.PRODUCTION,
            "production": RuntimeEnvironment.PRODUCTION,
        }
        normalized = str(value).strip().lower()
        if normalized not in aliases:
            allowed = "local, dev/development, test, staging, prod/production"
            raise ValueError(f"ENV/ENVIRONMENT must be one of: {allowed}")
        return aliases[normalized]

    @field_validator("database_url", "accounts_database_url", mode="before")
    @classmethod
    def fix_postgres_url(cls, value: str) -> str:
        """Normalize legacy provider URLs for SQLAlchemy 2."""

        if value and value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql://", 1)
        return value

    @field_validator(
        "identity_provider",
        "queue_provider",
        "processing_provider",
        "weather_provider",
        "satellite_provider",
        "gis_provider",
        "construction_provider",
        "asset_management_provider",
        "maritime_provider",
        "object_storage_provider",
        "erp_provider",
        "notification_provider",
        "paypal_mode",
        mode="before",
    )
    @classmethod
    def normalize_provider_name(cls, value: Any) -> str:
        normalized = str(value or "").strip().lower().replace("-", "_")
        if not _PROVIDER_NAME.fullmatch(normalized):
            raise ValueError("provider names must be stable lowercase identifiers")
        return normalized

    @field_validator("admin_emails", mode="before")
    @classmethod
    def normalize_admin_emails(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, tuple, set)):
            value = ",".join(str(item) for item in value)
        emails = []
        for raw_email in str(value).split(","):
            email = raw_email.strip().lower()
            if not email:
                continue
            if any(character in email for character in "\r\n") or "@" not in email:
                raise ValueError("ADMIN_EMAILS must contain comma-separated email addresses")
            emails.append(email)
        return ",".join(dict.fromkeys(emails))

    @field_validator("trusted_proxy_cidrs", mode="before")
    @classmethod
    def normalize_trusted_proxy_cidrs(cls, value: Any) -> str:
        """Validate the network peers allowed to supply forwarding headers."""

        if value is None:
            return ""
        if isinstance(value, (list, tuple, set)):
            value = ",".join(str(item) for item in value)
        networks: list[str] = []
        for raw_network in str(value).split(","):
            candidate = raw_network.strip()
            if not candidate:
                continue
            try:
                network = ipaddress.ip_network(candidate, strict=False)
            except ValueError as exc:
                raise ValueError(
                    "TRUSTED_PROXY_CIDRS must contain comma-separated IP networks"
                ) from exc
            networks.append(str(network))
        return ",".join(dict.fromkeys(networks))

    @field_validator("microsoft_tenant_id", mode="before")
    @classmethod
    def normalize_legacy_microsoft_tenant(cls, value: Any) -> str:
        return str(value or "common").strip().lower()

    @field_validator(
        "internal_token_issuer",
        "internal_token_audience",
        "entra_external_id_issuer",
        "entra_external_id_audience",
        "entra_external_id_tenant_id",
        "entra_external_id_discovery_url",
        "entra_external_id_required_scope",
        "entra_external_id_authorized_party",
        mode="before",
    )
    @classmethod
    def normalize_identity_value(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_security_profile(self) -> "Settings":
        if (
            self.env is not None
            and self.legacy_environment is not None
            and self.env is not self.legacy_environment
        ):
            raise ValueError("ENV and ENVIRONMENT must not select different profiles")
        self.env = (
            self.env
            or self.legacy_environment
            or RuntimeEnvironment.DEVELOPMENT
        )
        if self.paypal_mode not in {"sandbox", "live"}:
            raise ValueError("PAYPAL_MODE must be 'sandbox' or 'live'")
        if self.identity_provider not in {
            "internal",
            "transition",
            "entra_external_id",
        }:
            raise ValueError(
                "IDENTITY_PROVIDER must be internal, transition, or entra_external_id"
            )
        if not self.internal_token_issuer.strip() or not self.internal_token_audience.strip():
            raise ValueError("internal token issuer and audience must not be empty")

        entra_required = (
            self.entra_external_id_issuer,
            self.entra_external_id_audience,
            self.entra_external_id_tenant_id,
        )
        if any(entra_required) and not all(entra_required):
            raise ValueError(
                "Entra External ID issuer, audience, and tenant ID must be configured together"
            )
        if self.identity_provider in {"transition", "entra_external_id"} and not all(entra_required):
            raise ValueError(
                "external IDENTITY_PROVIDER requires Entra issuer, audience, and tenant ID"
            )
        if all(entra_required):
            try:
                self.entra_external_id_tenant_id = str(
                    uuid.UUID(self.entra_external_id_tenant_id)
                )
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValueError("ENTRA_EXTERNAL_ID_TENANT_ID must be a UUID") from exc
            if not self.entra_external_id_required_scope:
                raise ValueError(
                    "ENTRA_EXTERNAL_ID_REQUIRED_SCOPE must not be empty when Entra is configured"
                )
            audience = self.entra_external_id_audience.lower().rstrip("/")
            audience_without_api_prefix = audience.removeprefix("api://")
            if audience in {
                _MICROSOFT_GRAPH_APP_ID,
                _MICROSOFT_GRAPH_RESOURCE,
            } or audience_without_api_prefix == _MICROSOFT_GRAPH_APP_ID:
                raise ValueError(
                    "ENTRA_EXTERNAL_ID_AUDIENCE must identify the GeoVision API, "
                    "not Microsoft Graph"
                )
            required_scope = self.entra_external_id_required_scope.lower().rstrip("/")
            if required_scope == "user.read" or required_scope.startswith(
                f"{_MICROSOFT_GRAPH_RESOURCE}/"
            ):
                raise ValueError(
                    "ENTRA_EXTERNAL_ID_REQUIRED_SCOPE must be a GeoVision API scope, "
                    "not a Microsoft Graph scope"
                )
        for field_name, configured_url in (
            ("ENTRA_EXTERNAL_ID_ISSUER", self.entra_external_id_issuer),
            ("ENTRA_EXTERNAL_ID_DISCOVERY_URL", self.entra_external_id_discovery_url),
        ):
            if not configured_url:
                continue
            parsed = urlsplit(configured_url)
            if (
                not parsed.scheme
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    f"{field_name} must be an absolute URL without userinfo, query, or fragment"
                )
            if parsed.scheme.lower() != "https":
                raise ValueError(f"{field_name} must use HTTPS")
        if self.integration_retry_max_seconds < self.integration_retry_initial_seconds:
            raise ValueError(
                "INTEGRATION_RETRY_MAX_SECONDS must be greater than or equal to "
                "INTEGRATION_RETRY_INITIAL_SECONDS"
            )
        if self.is_deployed:
            for field_name, configured_url in (
                ("FRONTEND_BASE", self.frontend_base),
                ("BACKEND_BASE", self.backend_base),
            ):
                parsed = urlsplit(configured_url)
                if (
                    parsed.scheme.lower() != "https"
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                    or parsed.query
                    or parsed.fragment
                ):
                    raise ValueError(
                        f"{field_name} must be an absolute HTTPS URL without "
                        "userinfo, query, or fragment in staging and production"
                    )
            if (
                self.microsoft_client_id
                and self.microsoft_client_secret
                and self.microsoft_tenant_id in {"common", "organizations", "consumers"}
            ):
                raise ValueError(
                    "MICROSOFT_TENANT_ID must pin the deployed legacy callback"
                )
            if self.secret_key_is_insecure:
                raise ValueError(
                    "SECRET_KEY must be a non-placeholder value of at least 32 characters "
                    "in staging and production"
                )
            if not self.encryption_key_is_valid:
                raise ValueError(
                    "ENCRYPTION_KEY must be a valid Fernet key in staging and production"
                )
            has_admin_emails = bool(self.admin_email_list)
            has_admin_password = bool((self.admin_password or "").strip())
            if has_admin_emails != has_admin_password:
                raise ValueError(
                    "ADMIN_EMAILS and ADMIN_PASSWORD must be configured together "
                    "in staging and production"
                )
            if has_admin_password:
                try:
                    validate_admin_password(self.admin_password or "")
                except ValueError as exc:
                    raise ValueError(
                        "ADMIN_PASSWORD does not meet the privileged bootstrap policy"
                    ) from exc
        return self

    @property
    def environment_name(self) -> str:
        return self.env.value if isinstance(self.env, RuntimeEnvironment) else str(self.env)

    @property
    def is_production(self) -> bool:
        return self.environment_name.lower() in {"prod", "production"}

    @property
    def is_staging(self) -> bool:
        return self.environment_name.lower() in {"stage", "staging"}

    @property
    def is_deployed(self) -> bool:
        return self.is_staging or self.is_production

    @property
    def secret_key_is_insecure(self) -> bool:
        normalized = (self.secret_key or "").strip().lower()
        return len(normalized) < 32 or any(marker in normalized for marker in _INSECURE_MARKERS)

    @property
    def encryption_key_is_valid(self) -> bool:
        key = (self.encryption_key or "").strip()
        if not key:
            return False
        try:
            decoded = base64.b64decode(key.encode(), altchars=b"-_", validate=True)
            return len(decoded) == 32
        except (ValueError, TypeError):
            return False

    @property
    def cors_origin_list(self) -> tuple[str, ...]:
        return tuple(
            origin.strip().rstrip("/")
            for origin in self.cors_origins.split(",")
            if origin.strip()
        )

    @property
    def trusted_proxy_networks(
        self,
    ) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
        return tuple(
            ipaddress.ip_network(network, strict=False)
            for network in self.trusted_proxy_cidrs.split(",")
            if network
        )

    @property
    def admin_email_list(self) -> tuple[str, ...]:
        return tuple(email for email in self.admin_emails.split(",") if email)

    @property
    def entra_external_id_configuration_complete(self) -> bool:
        return bool(
            self.entra_external_id_issuer
            and self.entra_external_id_audience
            and self.entra_external_id_tenant_id
            and self.entra_external_id_required_scope
        )

    @property
    def effective_entra_external_id_discovery_url(self) -> Optional[str]:
        if self.entra_external_id_discovery_url:
            return self.entra_external_id_discovery_url
        if not self.entra_external_id_issuer:
            return None
        return (
            self.entra_external_id_issuer.rstrip("/")
            + "/.well-known/openid-configuration"
        )

    @property
    def effective_s3_bucket(self) -> str:
        return self.s3_bucket or "geovision-datasets"

    @property
    def smtp_configuration_complete(self) -> bool:
        username_configured = bool(self.smtp_user and self.smtp_user.strip())
        password_configured = bool(self.smtp_password)
        return bool(
            self.smtp_host
            and self.smtp_host.strip()
            and self.smtp_from
            and self.smtp_from.strip()
            and username_configured == password_configured
        )

    @property
    def multicaixa_configuration_complete(self) -> bool:
        return bool(self.multicaixa_merchant_id and self.multicaixa_api_key)

    @property
    def database_driver(self) -> str:
        scheme = urlsplit(self.database_url).scheme
        return scheme.split("+", 1)[0] if scheme else "unknown"

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Return a redacted dump safe for diagnostics and support output."""

        data = super().model_dump(*args, **kwargs)
        for field_name in self._SECRET_FIELDS:
            if field_name in data and data[field_name] not in (None, ""):
                data[field_name] = "[REDACTED]"
        for field_name in _URL_FIELDS:
            if field_name in data and data[field_name]:
                data[field_name] = _safe_origin(str(data[field_name]))
        if data.get("cors_origins"):
            data["cors_origins"] = ",".join(
                _safe_origin(origin) for origin in self.cors_origin_list
            )
        return data

    def model_dump_json(self, *, indent: int | None = None, **kwargs: Any) -> str:
        """Serialize the same redacted representation used by ``model_dump``."""

        return json.dumps(
            self.model_dump(**kwargs),
            default=str,
            indent=indent,
        )

    def safe_summary(self) -> dict[str, Any]:
        """Return diagnostics that cannot contain credentials or database URLs."""

        return {
            "app_name": self.app_name,
            "app_version": self.app_version,
            "environment": self.environment_name,
            "backend_base": _safe_origin(self.backend_base),
            "frontend_base": _safe_origin(self.frontend_base),
            "cors_origins": [_safe_origin(origin) for origin in self.cors_origin_list],
            "database_driver": self.database_driver,
            "providers": {
                "identity": self.identity_provider,
                "object_storage": self.object_storage_provider,
                "queue": self.queue_provider,
                "processing": self.processing_provider,
                "weather": self.weather_provider,
                "satellite": self.satellite_provider,
                "gis": self.gis_provider,
                "construction": self.construction_provider,
                "asset_management": self.asset_management_provider,
                "maritime": self.maritime_provider,
                "erp": self.erp_provider,
                "notifications": self.notification_provider,
            },
            "configured": {
                "google_oauth": bool(self.google_client_id and self.google_client_secret),
                "microsoft_oauth": bool(
                    self.microsoft_client_id and self.microsoft_client_secret
                ),
                "entra_external_id": self.entra_external_id_configuration_complete,
                "openai": bool(self.openai_api_key),
                "smtp": bool(
                    self.smtp_configuration_complete
                    and (not self.is_deployed or self.smtp_use_tls)
                ),
                "s3": bool(self.s3_bucket),
                "erpnext": bool(
                    self.erpnext_base_url
                    and self.erpnext_api_key
                    and self.erpnext_api_secret
                ),
                "multicaixa": self.multicaixa_configuration_complete,
                "stripe": bool(self.stripe_secret_key),
                "paypal": bool(self.paypal_client_id and self.paypal_secret),
                "mqtt": self.mqtt_enabled,
            },
        }


settings = Settings()

# Local/development/test can use an ephemeral JWT key. Production is rejected
# by Settings validation before this point.
if settings.secret_key_is_insecure:
    warnings.warn(
        "SECRET_KEY not set or insecure — using a random ephemeral key. "
        "Set a stable 32+ character SECRET_KEY before deploying.",
        stacklevel=1,
    )
    settings.secret_key = secrets.token_urlsafe(48)

# Backward-compatible names expected by scripts and Alembic.
JWT_SECRET = settings.secret_key
JWT_ALG = settings.algorithm
JWT_EXPIRE_MIN = settings.access_token_expires_minutes
OPENAI_API_KEY = settings.openai_api_key
DATABASE_URL = settings.database_url


__all__ = [
    "DATABASE_URL",
    "JWT_ALG",
    "JWT_EXPIRE_MIN",
    "JWT_SECRET",
    "OPENAI_API_KEY",
    "RuntimeEnvironment",
    "Settings",
    "settings",
]
