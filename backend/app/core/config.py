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
        "odoo_base_url",
        "frontend_base",
        "multicaixa_api_url",
        "multicaixa_callback_url",
        "paypal_cancel_url",
        "paypal_return_url",
        "s3_endpoint_url",
        "azure_storage_account_url",
        "azure_app_configuration_endpoint",
        "nodeodm_base_url",
        "copernicus_stac_base_url",
        "aemet_base_url",
        "miteco_ogc_features_base_url",
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
    log_level: str = "INFO"
    observability_exporter: str = "console"
    applicationinsights_connection_string: Optional[str] = Field(
        default=None,
        repr=False,
    )
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
    run_migrations_on_startup: bool = True
    startup_compatibility_bootstrap: bool = True
    readiness_require_current_schema: bool = False

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
    report_narrative_provider: str = "deterministic"
    report_narrative_model: Optional[str] = None

    # Durable events. Database delivery is self-contained for local/dev/test;
    # deployed workers may publish the same envelope to Azure Service Bus.
    queue_provider: str = "database"
    event_topic: str = "geovision.domain.v1"
    event_worker_in_process: bool = False
    event_worker_poll_seconds: float = Field(default=1.0, gt=0, le=60)
    event_worker_batch_size: int = Field(default=50, ge=1, le=500)
    event_worker_max_attempts: int = Field(default=8, ge=1, le=50)
    event_worker_claim_timeout_seconds: int = Field(default=300, ge=30, le=3600)
    event_retry_initial_seconds: float = Field(default=1.0, ge=0, le=3600)
    event_retry_max_seconds: float = Field(default=300.0, ge=0, le=86400)
    service_bus_fully_qualified_namespace: Optional[str] = None
    service_bus_connection_string: Optional[str] = Field(default=None, repr=False)
    service_bus_topic: str = "geovision-events"
    service_bus_subscription: str = "geovision-workers"
    azure_event_grid_enabled: bool = False
    azure_event_grid_webhook_secret: Optional[str] = Field(default=None, repr=False)
    azure_event_grid_subscription_name: Optional[str] = None
    iot_cloud_provider: str = "none"
    azure_iot_hub_enabled: bool = False
    azure_iot_hub_webhook_secret: Optional[str] = Field(default=None, repr=False)
    azure_iot_hub_name: Optional[str] = None
    processing_provider: str = "none"
    processing_auto_create_enabled: bool = False
    processing_default_outputs: str = "ORTHOMOSAIC,DSM,POINT_CLOUD"
    processing_worker_in_process: bool = False
    processing_worker_poll_seconds: float = Field(default=5.0, gt=0, le=300)
    processing_worker_batch_size: int = Field(default=5, ge=1, le=50)
    processing_worker_claim_timeout_seconds: int = Field(default=1800, ge=60, le=86400)
    processing_default_max_retries: int = Field(default=3, ge=0, le=20)
    processing_retry_initial_seconds: float = Field(default=10.0, ge=0, le=3600)
    processing_retry_max_seconds: float = Field(default=900.0, ge=0, le=86400)
    processing_minimum_images: int = Field(default=2, ge=2, le=100_000)
    processing_max_input_bytes: int = Field(
        default=1024 * 1024 * 1024, ge=1, le=20 * 1024 * 1024 * 1024
    )
    processing_max_output_archive_bytes: int = Field(
        default=1024 * 1024 * 1024, ge=1, le=20 * 1024 * 1024 * 1024
    )
    processing_max_output_unpacked_bytes: int = Field(
        default=2 * 1024 * 1024 * 1024, ge=1, le=40 * 1024 * 1024 * 1024
    )
    processing_max_output_files: int = Field(default=500, ge=1, le=20_000)
    processing_provider_read_timeout_seconds: float = Field(
        default=300.0, gt=0, le=86400
    )
    processing_provider_write_timeout_seconds: float = Field(
        default=3600.0, gt=0, le=86400
    )
    nodeodm_base_url: Optional[str] = None
    nodeodm_token: Optional[str] = Field(default=None, repr=False)
    weather_provider: str = "none"
    satellite_provider: str = "none"
    intelligence_worker_in_process: bool = False
    intelligence_worker_poll_seconds: float = Field(default=30.0, gt=0, le=3600)
    intelligence_worker_batch_size: int = Field(default=10, ge=1, le=100)
    intelligence_worker_claim_timeout_seconds: int = Field(default=600, ge=30, le=86400)
    intelligence_max_attempts: int = Field(default=3, ge=1, le=20)
    intelligence_retry_initial_seconds: float = Field(default=30.0, ge=0, le=86400)
    intelligence_retry_max_seconds: float = Field(default=3600.0, ge=0, le=604800)
    satellite_cache_ttl_seconds: int = Field(default=21600, ge=60, le=604800)
    weather_cache_ttl_seconds: int = Field(default=1800, ge=60, le=86400)
    satellite_default_collection: str = "sentinel-2-l2a"
    satellite_default_lookback_days: int = Field(default=14, ge=1, le=366)
    satellite_default_max_cloud_cover_percent: float = Field(default=60.0, ge=0, le=100)
    satellite_max_scenes_per_request: int = Field(default=20, ge=1, le=100)
    satellite_download_assets_enabled: bool = False
    satellite_download_asset_keys: str = "thumbnail"
    satellite_max_asset_bytes: int = Field(
        default=256 * 1024 * 1024, ge=1, le=5 * 1024 * 1024 * 1024
    )
    copernicus_stac_base_url: str = "https://stac.dataspace.copernicus.eu/v1"
    copernicus_access_token: Optional[str] = Field(default=None, repr=False)
    copernicus_allowed_download_hosts: str = (
        "download.dataspace.copernicus.eu,datahub.creodias.eu"
    )
    weather_default_lookback_hours: int = Field(default=12, ge=1, le=168)
    aemet_base_url: str = "https://opendata.aemet.es/opendata"
    aemet_api_key: Optional[str] = Field(default=None, repr=False)
    aemet_max_station_distance_km: float = Field(default=150.0, gt=0, le=1000)
    gis_provider: str = "none"
    miteco_ogc_features_base_url: str = (
        "https://gis.miteco.gob.es/geoserver/ogc/features/v1"
    )
    miteco_gis_max_features: int = Field(default=100, ge=1, le=100)
    miteco_gis_max_response_bytes: int = Field(
        default=2 * 1024 * 1024,
        ge=1024,
        le=16 * 1024 * 1024,
    )
    construction_provider: str = "none"
    asset_management_provider: str = "none"
    maritime_provider: str = "none"

    # Optional enterprise adapter credentials. Scaffolds remain fail closed;
    # setting these values does not activate live connectivity.
    autodesk_aps_client_id: Optional[str] = Field(default=None, repr=False)
    autodesk_aps_client_secret: Optional[str] = Field(default=None, repr=False)
    procore_client_id: Optional[str] = Field(default=None, repr=False)
    procore_client_secret: Optional[str] = Field(default=None, repr=False)
    bentley_itwin_client_id: Optional[str] = Field(default=None, repr=False)
    bentley_itwin_client_secret: Optional[str] = Field(default=None, repr=False)
    trimble_client_id: Optional[str] = Field(default=None, repr=False)
    trimble_client_secret: Optional[str] = Field(default=None, repr=False)
    arcgis_client_id: Optional[str] = Field(default=None, repr=False)
    arcgis_client_secret: Optional[str] = Field(default=None, repr=False)
    seequent_client_id: Optional[str] = Field(default=None, repr=False)
    seequent_client_secret: Optional[str] = Field(default=None, repr=False)

    # Shared integration timeout/retry conventions.
    integration_connect_timeout_seconds: float = Field(default=5.0, gt=0)
    integration_read_timeout_seconds: float = Field(default=30.0, gt=0)
    integration_retry_attempts: int = Field(default=3, ge=1, le=10)
    integration_retry_initial_seconds: float = Field(default=0.5, ge=0)
    integration_retry_max_seconds: float = Field(default=8.0, ge=0)

    # Object storage. Local development is filesystem-backed while deployed
    # environments can select Azure Blob or an S3-compatible adapter.
    object_storage_provider: str = "local"
    local_storage_root: Path = Path("./data/object-storage")
    dataset_direct_upload_max_bytes: int = Field(
        default=500 * 1024 * 1024, ge=1, le=5 * 1024 * 1024 * 1024
    )
    dataset_signed_upload_max_bytes: int = Field(
        # Keep the portable signed-PUT path below both S3's single-PUT limit
        # and Azure Block Blob's single-request ceiling. Larger workloads must
        # use a future explicit multipart/block session rather than a URL that
        # only appears to support them.
        default=4 * 1024 * 1024 * 1024,
        ge=1,
        le=5 * 1024 * 1024 * 1024,
    )
    dataset_signed_url_expiry_seconds: int = Field(default=900, ge=60, le=3600)
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
    azure_storage_account_url: Optional[str] = None
    azure_storage_container: str = "geovision-datasets"
    azure_storage_connection_string: Optional[str] = Field(default=None, repr=False)
    azure_storage_account_name: Optional[str] = None
    azure_storage_account_key: Optional[str] = Field(default=None, repr=False)
    azure_managed_identity_client_id: Optional[str] = None

    # Read-only rollout configuration. Authorization, entitlement, and an
    # active connection remain separate mandatory gates.
    azure_app_configuration_endpoint: Optional[str] = None
    integration_feature_flag_refresh_seconds: int = Field(default=300, ge=1, le=3600)
    integration_feature_flag_max_staleness_seconds: int = Field(
        default=3600, ge=1, le=86400
    )
    integration_feature_flag_startup_timeout_seconds: int = Field(
        default=5, ge=1, le=30
    )

    # ERP integration. GeoVision remains the system of record.
    erp_provider: str = "mock"
    erpnext_base_url: Optional[str] = Field(default=None, repr=False)
    erpnext_api_key: Optional[str] = Field(default=None, repr=False)
    erpnext_api_secret: Optional[str] = Field(default=None, repr=False)
    erpnext_webhook_secret: Optional[str] = Field(default=None, repr=False)
    odoo_base_url: Optional[str] = Field(default=None, repr=False)
    odoo_database: Optional[str] = None
    odoo_api_key: Optional[str] = Field(default=None, repr=False)
    odoo_webhook_secret: Optional[str] = Field(default=None, repr=False)
    odoo_bridge_model: str = "geovision.integration.bridge"
    odoo_bridge_method: str = "sync_from_geovision"
    erp_worker_poll_seconds: float = Field(default=5.0, gt=0, le=300)
    erp_worker_batch_size: int = Field(default=50, ge=1, le=500)
    erp_worker_claim_timeout_seconds: int = Field(default=300, ge=30, le=3600)
    erp_callback_replay_window_seconds: int = Field(default=300, ge=30, le=3600)

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
    notification_worker_poll_seconds: float = Field(default=5.0, gt=0, le=300)
    notification_worker_batch_size: int = Field(default=50, ge=1, le=500)
    notification_worker_claim_timeout_seconds: int = Field(default=300, ge=30, le=3600)
    notification_worker_retry_base_seconds: float = Field(default=30.0, ge=0, le=3600)
    notification_worker_retry_max_seconds: float = Field(default=3600.0, ge=0, le=86400)
    notification_delivery_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    azure_notification_hubs_namespace: Optional[str] = None
    azure_notification_hubs_hub_name: Optional[str] = None
    azure_notification_hubs_sas_key_name: Optional[str] = None
    azure_notification_hubs_sas_key: Optional[str] = Field(default=None, repr=False)

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
    iot_watchdog_in_process: bool = False
    iot_watchdog_interval_seconds: int = Field(default=30, ge=5, le=3600)
    iot_message_max_age_seconds: int = Field(default=300, ge=1)
    iot_offline_after_seconds: int = Field(default=120, ge=1)
    iot_command_ttl_seconds: int = Field(default=300, ge=1)
    iot_max_messages_per_minute: int = Field(default=120, ge=1)
    iot_raw_retention_days: int = Field(default=30, ge=1)
    iot_aggregate_retention_days: int = Field(default=730, ge=1)
    iot_store_forward_max_age_days: int = Field(default=30, ge=1, le=365)

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
            "applicationinsights_connection_string",
            "service_bus_connection_string",
            "azure_event_grid_webhook_secret",
            "azure_iot_hub_webhook_secret",
            "nodeodm_token",
            "copernicus_access_token",
            "aemet_api_key",
            "autodesk_aps_client_id",
            "autodesk_aps_client_secret",
            "procore_client_id",
            "procore_client_secret",
            "bentley_itwin_client_id",
            "bentley_itwin_client_secret",
            "trimble_client_id",
            "trimble_client_secret",
            "arcgis_client_id",
            "arcgis_client_secret",
            "seequent_client_id",
            "seequent_client_secret",
            "s3_access_key_id",
            "s3_secret_access_key",
            "azure_storage_connection_string",
            "azure_storage_account_key",
            "erpnext_api_key",
            "erpnext_api_secret",
            "erpnext_webhook_secret",
            "odoo_api_key",
            "odoo_webhook_secret",
            "smtp_password",
            "azure_notification_hubs_sas_key",
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

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: Any) -> str:
        normalized = str(value or "INFO").strip().upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(
                "LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL"
            )
        return normalized

    @field_validator("observability_exporter", mode="before")
    @classmethod
    def normalize_observability_exporter(cls, value: Any) -> str:
        normalized = str(value or "console").strip().lower().replace("-", "_")
        if normalized not in {"console", "azure_monitor", "none"}:
            raise ValueError(
                "OBSERVABILITY_EXPORTER must be console, azure_monitor, or none"
            )
        return normalized

    @field_validator(
        "identity_provider",
        "queue_provider",
        "iot_cloud_provider",
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
        "report_narrative_provider",
        "paypal_mode",
        mode="before",
    )
    @classmethod
    def normalize_provider_name(cls, value: Any) -> str:
        normalized = str(value or "").strip().lower().replace("-", "_")
        if not _PROVIDER_NAME.fullmatch(normalized):
            raise ValueError("provider names must be stable lowercase identifiers")
        return normalized

    @field_validator("satellite_download_asset_keys", mode="before")
    @classmethod
    def normalize_satellite_asset_keys(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, tuple, set)):
            value = ",".join(str(item) for item in value)
        return ",".join(
            dict.fromkeys(
                item.strip() for item in str(value).split(",") if item.strip()
            )
        )

    @field_validator("copernicus_allowed_download_hosts", mode="before")
    @classmethod
    def normalize_copernicus_hosts(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, tuple, set)):
            value = ",".join(str(item) for item in value)
        return ",".join(
            dict.fromkeys(
                item.strip().lower().rstrip(".")
                for item in str(value).split(",")
                if item.strip()
            )
        )

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
                raise ValueError(
                    "ADMIN_EMAILS must contain comma-separated email addresses"
                )
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

    @field_validator("azure_app_configuration_endpoint", mode="before")
    @classmethod
    def normalize_app_configuration_endpoint(cls, value: Any) -> Optional[str]:
        if value is None or not str(value).strip():
            return None
        normalized = str(value).strip().rstrip("/")
        parsed = urlsplit(normalized)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.hostname.endswith(".azconfig.io")
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "AZURE_APP_CONFIGURATION_ENDPOINT must be a canonical Azure HTTPS origin"
            )
        return normalized

    @model_validator(mode="after")
    def validate_security_profile(self) -> "Settings":
        if (
            self.env is not None
            and self.legacy_environment is not None
            and self.env is not self.legacy_environment
        ):
            raise ValueError("ENV and ENVIRONMENT must not select different profiles")
        self.env = self.env or self.legacy_environment or RuntimeEnvironment.DEVELOPMENT
        if self.paypal_mode not in {"sandbox", "live"}:
            raise ValueError("PAYPAL_MODE must be 'sandbox' or 'live'")
        if (
            self.integration_feature_flag_max_staleness_seconds
            < self.integration_feature_flag_refresh_seconds
        ):
            raise ValueError(
                "INTEGRATION_FEATURE_FLAG_MAX_STALENESS_SECONDS must be greater "
                "than or equal to INTEGRATION_FEATURE_FLAG_REFRESH_SECONDS"
            )
        if self.report_narrative_provider not in {
            "deterministic",
            "mock",
            "azure_openai",
            "openai",
        }:
            raise ValueError(
                "REPORT_NARRATIVE_PROVIDER must be deterministic, mock, azure_openai, or openai"
            )
        if self.queue_provider not in {
            "database",
            "in_memory",
            "azure_service_bus",
            "null",
        }:
            raise ValueError(
                "QUEUE_PROVIDER must be database, in_memory, azure_service_bus, or null"
            )
        if self.iot_cloud_provider not in {"none", "null", "azure_iot_hub"}:
            raise ValueError("IOT_CLOUD_PROVIDER must be none or azure_iot_hub")
        if self.azure_iot_hub_enabled and self.iot_cloud_provider != "azure_iot_hub":
            raise ValueError(
                "AZURE_IOT_HUB_ENABLED requires IOT_CLOUD_PROVIDER=azure_iot_hub"
            )
        if self.azure_iot_hub_name and not re.fullmatch(
            r"[A-Za-z0-9](?:[A-Za-z0-9-]{1,48}[A-Za-z0-9])?",
            self.azure_iot_hub_name,
        ):
            raise ValueError("AZURE_IOT_HUB_NAME is invalid")
        if self.iot_store_forward_max_age_days > self.iot_raw_retention_days:
            raise ValueError(
                "IOT_STORE_FORWARD_MAX_AGE_DAYS must not exceed IOT_RAW_RETENTION_DAYS"
            )
        if self.event_retry_max_seconds < self.event_retry_initial_seconds:
            raise ValueError(
                "EVENT_RETRY_MAX_SECONDS must be greater than or equal to "
                "EVENT_RETRY_INITIAL_SECONDS"
            )
        if self.processing_retry_max_seconds < self.processing_retry_initial_seconds:
            raise ValueError(
                "PROCESSING_RETRY_MAX_SECONDS must be greater than or equal to "
                "PROCESSING_RETRY_INITIAL_SECONDS"
            )
        if (
            self.intelligence_retry_max_seconds
            < self.intelligence_retry_initial_seconds
        ):
            raise ValueError(
                "INTELLIGENCE_RETRY_MAX_SECONDS must be greater than or equal to "
                "INTELLIGENCE_RETRY_INITIAL_SECONDS"
            )
        processing_providers = {
            "none",
            "null",
            "fake",
            "deterministic",
            "nodeodm",
            "opendronemap",
            "pix4d",
            "autodesk_reality_capture",
            "bentley_reality_modeling",
        }
        if self.processing_provider not in processing_providers:
            raise ValueError(
                "PROCESSING_PROVIDER must select the deterministic, NodeODM, or a "
                "documented future adapter"
            )
        outputs = tuple(
            dict.fromkeys(
                item.strip().upper().replace("-", "_")
                for item in self.processing_default_outputs.split(",")
                if item.strip()
            )
        )
        supported_outputs = {
            "ORTHOMOSAIC",
            "DSM",
            "DTM",
            "POINT_CLOUD",
            "MESH_3D",
            "NDVI",
            "NDRE",
            "GNDVI",
        }
        if not outputs or not set(outputs).issubset(supported_outputs):
            raise ValueError(
                "PROCESSING_DEFAULT_OUTPUTS contains an unsupported output type"
            )
        self.processing_default_outputs = ",".join(outputs)
        if self.nodeodm_base_url:
            parsed = urlsplit(self.nodeodm_base_url)
            allowed_schemes = {"https"} if self.is_deployed else {"http", "https"}
            if (
                parsed.scheme.lower() not in allowed_schemes
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "NODEODM_BASE_URL must be an absolute provider URL without "
                    "userinfo, query, or fragment"
                )
            self.nodeodm_base_url = self.nodeodm_base_url.rstrip("/")
        if self.processing_provider in {"nodeodm", "opendronemap"} and not (
            self.nodeodm_base_url
        ):
            raise ValueError("NodeODM processing requires NODEODM_BASE_URL")
        satellite_providers = {
            "none",
            "null",
            "fake",
            "deterministic",
            "copernicus",
            "cdse",
            "sentinel",
        }
        if self.satellite_provider not in satellite_providers:
            raise ValueError("SATELLITE_PROVIDER must be none, fake, or copernicus")
        weather_providers = {
            "none",
            "null",
            "fake",
            "deterministic",
            "aemet",
            "aemet_opendata",
            "azure_maps",
            "azure_maps_weather",
        }
        if self.weather_provider not in weather_providers:
            raise ValueError(
                "WEATHER_PROVIDER must be none, fake, aemet, or the Azure Maps scaffold"
            )
        if (
            self.weather_provider in {"aemet", "aemet_opendata"}
            and not self.aemet_api_key
        ):
            raise ValueError("AEMET weather requires AEMET_API_KEY")
        construction_providers = {
            "none",
            "null",
            "fake",
            "deterministic",
            "autodesk_aps",
            "procore",
            "bentley_itwin",
            "trimble",
        }
        if self.construction_provider not in construction_providers:
            raise ValueError(
                "CONSTRUCTION_PROVIDER must be none, fake, autodesk_aps, procore, "
                "bentley_itwin, or trimble"
            )
        gis_providers = {
            "none",
            "null",
            "fake",
            "deterministic",
            "arcgis",
            "miteco",
        }
        if self.gis_provider not in gis_providers:
            raise ValueError("GIS_PROVIDER must be none, fake, arcgis, or miteco")
        asset_management_providers = {
            "none",
            "null",
            "fake",
            "deterministic",
            "seequent",
            "mine_enterprise",
            "sap_eam",
            "ibm_maximo",
            "dynamics_365_asset_management",
            "customer_cmms",
        }
        if self.asset_management_provider not in asset_management_providers:
            raise ValueError(
                "ASSET_MANAGEMENT_PROVIDER must be none, null, fake, "
                "deterministic, seequent, mine_enterprise, sap_eam, ibm_maximo, "
                "dynamics_365_asset_management, or customer_cmms"
            )
        maritime_providers = {
            "none",
            "null",
            "fake",
            "deterministic",
            "marinetraffic",
            "kpler",
            "puertos_del_estado",
        }
        if self.maritime_provider not in maritime_providers:
            raise ValueError(
                "MARITIME_PROVIDER must be none, null, fake, deterministic, "
                "marinetraffic, kpler, or puertos_del_estado"
            )
        if not re.fullmatch(
            r"[a-z0-9][a-z0-9._-]{1,119}", self.satellite_default_collection
        ):
            raise ValueError("SATELLITE_DEFAULT_COLLECTION is invalid")
        asset_keys = self.satellite_download_asset_key_list
        if self.satellite_download_assets_enabled and not asset_keys:
            raise ValueError(
                "SATELLITE_DOWNLOAD_ASSET_KEYS is required when asset downloads are enabled"
            )
        if any(
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}", key)
            for key in asset_keys
        ):
            raise ValueError("SATELLITE_DOWNLOAD_ASSET_KEYS contains an invalid key")
        hosts = self.copernicus_download_host_list
        if not hosts or any(
            "/" in host
            or ":" in host
            or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host)
            for host in hosts
        ):
            raise ValueError(
                "COPERNICUS_ALLOWED_DOWNLOAD_HOSTS contains an invalid host"
            )
        for field_name, configured_url in (
            ("COPERNICUS_STAC_BASE_URL", self.copernicus_stac_base_url),
            ("AEMET_BASE_URL", self.aemet_base_url),
        ):
            parsed = urlsplit(configured_url)
            allowed_schemes = {"https"} if self.is_deployed else {"http", "https"}
            if (
                parsed.scheme.lower() not in allowed_schemes
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    f"{field_name} must be an absolute provider URL without "
                    "userinfo, query, or fragment"
                )
        self.copernicus_stac_base_url = self.copernicus_stac_base_url.rstrip("/")
        self.aemet_base_url = self.aemet_base_url.rstrip("/")
        parsed_miteco = urlsplit(self.miteco_ogc_features_base_url)
        if (
            parsed_miteco.scheme.lower() != "https"
            or parsed_miteco.hostname != "gis.miteco.gob.es"
            or parsed_miteco.port not in {None, 443}
            or parsed_miteco.username
            or parsed_miteco.password
            or parsed_miteco.query
            or parsed_miteco.fragment
            or parsed_miteco.path.rstrip("/") != "/geoserver/ogc/features/v1"
        ):
            raise ValueError(
                "MITECO_OGC_FEATURES_BASE_URL must use the reviewed official "
                "HTTPS origin and path"
            )
        self.miteco_ogc_features_base_url = (
            "https://gis.miteco.gob.es/geoserver/ogc/features/v1"
        )
        if not self.event_topic.strip() or not self.service_bus_topic.strip():
            raise ValueError("event and Service Bus topic names must not be empty")
        if not self.service_bus_subscription.strip():
            raise ValueError("SERVICE_BUS_SUBSCRIPTION must not be empty")
        if self.service_bus_fully_qualified_namespace:
            namespace = self.service_bus_fully_qualified_namespace.strip().lower()
            if (
                "://" in namespace
                or "/" in namespace
                or not namespace.endswith(".servicebus.windows.net")
            ):
                raise ValueError(
                    "SERVICE_BUS_FULLY_QUALIFIED_NAMESPACE must be an Azure Service Bus host name"
                )
            self.service_bus_fully_qualified_namespace = namespace
        if self.queue_provider == "azure_service_bus" and not (
            self.service_bus_connection_string
            or self.service_bus_fully_qualified_namespace
        ):
            raise ValueError(
                "Azure Service Bus queue delivery requires a connection string or namespace"
            )
        if self.identity_provider not in {
            "internal",
            "transition",
            "entra_external_id",
        }:
            raise ValueError(
                "IDENTITY_PROVIDER must be internal, transition, or entra_external_id"
            )
        if (
            not self.internal_token_issuer.strip()
            or not self.internal_token_audience.strip()
        ):
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
        if self.identity_provider in {"transition", "entra_external_id"} and not all(
            entra_required
        ):
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
            if (
                audience
                in {
                    _MICROSOFT_GRAPH_APP_ID,
                    _MICROSOFT_GRAPH_RESOURCE,
                }
                or audience_without_api_prefix == _MICROSOFT_GRAPH_APP_ID
            ):
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
        if self.erp_provider not in {"mock", "erpnext", "odoo"}:
            raise ValueError("ERP_PROVIDER must be mock, erpnext, or odoo")
        if not re.fullmatch(r"[a-z][a-z0-9_.]{1,118}[a-z0-9]", self.odoo_bridge_model):
            raise ValueError("ODOO_BRIDGE_MODEL must be a technical model identifier")
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,118}[a-z0-9]", self.odoo_bridge_method):
            raise ValueError("ODOO_BRIDGE_METHOD must be a technical method identifier")
        if self.odoo_base_url:
            parsed = urlsplit(self.odoo_base_url)
            allowed_schemes = {"https"} if self.is_deployed else {"http", "https"}
            if (
                parsed.scheme.lower() not in allowed_schemes
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.path not in {"", "/"}
            ):
                raise ValueError(
                    "ODOO_BASE_URL must be an origin-only provider URL without credentials"
                )
            self.odoo_base_url = self.odoo_base_url.rstrip("/")
        if self.erp_provider == "odoo" and not all(
            (self.odoo_base_url, self.odoo_database, self.odoo_api_key)
        ):
            raise ValueError(
                "ERP_PROVIDER=odoo requires ODOO_BASE_URL, ODOO_DATABASE, and ODOO_API_KEY"
            )
        if self.is_deployed:
            if self.queue_provider in {"null", "in_memory"}:
                raise ValueError(
                    "deployed environments require database or azure_service_bus queue delivery"
                )
            if self.azure_event_grid_enabled and (
                not self.azure_event_grid_webhook_secret
                or len(self.azure_event_grid_webhook_secret) < 32
            ):
                raise ValueError(
                    "AZURE_EVENT_GRID_WEBHOOK_SECRET must contain at least 32 characters "
                    "when Event Grid ingestion is enabled in a deployed environment"
                )
            if self.azure_iot_hub_enabled and (
                not self.azure_iot_hub_webhook_secret
                or len(self.azure_iot_hub_webhook_secret) < 32
                or not self.azure_iot_hub_name
            ):
                raise ValueError(
                    "Deployed Azure IoT Hub ingress requires AZURE_IOT_HUB_NAME and "
                    "a 32+ character AZURE_IOT_HUB_WEBHOOK_SECRET"
                )
            if self.processing_auto_create_enabled and self.processing_provider in {
                "none",
                "null",
                "fake",
                "deterministic",
                "pix4d",
                "autodesk_reality_capture",
                "bentley_reality_modeling",
            }:
                raise ValueError(
                    "deployed automatic processing requires the configured NodeODM adapter"
                )
            if self.satellite_provider in {"fake", "deterministic"}:
                raise ValueError(
                    "deployed environments cannot use the fake satellite provider"
                )
            if self.weather_provider in {"fake", "deterministic"}:
                raise ValueError(
                    "deployed environments cannot use the fake weather provider"
                )
            if self.construction_provider in {"fake", "deterministic"}:
                raise ValueError(
                    "deployed environments cannot use the fake construction provider"
                )
            if self.gis_provider in {"fake", "deterministic"}:
                raise ValueError(
                    "deployed environments cannot use the fake GIS provider"
                )
            if self.asset_management_provider in {"fake", "deterministic"}:
                raise ValueError(
                    "deployed environments cannot use the fake asset-management provider"
                )
            if self.maritime_provider in {"fake", "deterministic"}:
                raise ValueError(
                    "deployed environments cannot use the fake maritime provider"
                )
            if self.erp_provider == "odoo" and (
                not self.odoo_webhook_secret or len(self.odoo_webhook_secret) < 32
            ):
                raise ValueError(
                    "deployed Odoo integration requires a 32+ character "
                    "ODOO_WEBHOOK_SECRET"
                )
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
        return (
            self.env.value
            if isinstance(self.env, RuntimeEnvironment)
            else str(self.env)
        )

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
        return len(normalized) < 32 or any(
            marker in normalized for marker in _INSECURE_MARKERS
        )

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
    def processing_default_output_list(self) -> tuple[str, ...]:
        return tuple(
            item for item in self.processing_default_outputs.split(",") if item
        )

    @property
    def satellite_download_asset_key_list(self) -> tuple[str, ...]:
        return tuple(
            item for item in self.satellite_download_asset_keys.split(",") if item
        )

    @property
    def copernicus_download_host_list(self) -> tuple[str, ...]:
        return tuple(
            item for item in self.copernicus_allowed_download_hosts.split(",") if item
        )

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

    @staticmethod
    def _client_credentials_complete(
        client_id: Optional[str],
        client_secret: Optional[str],
    ) -> bool:
        return bool(
            client_id and client_id.strip() and client_secret and client_secret.strip()
        )

    @property
    def autodesk_aps_configuration_complete(self) -> bool:
        return self._client_credentials_complete(
            self.autodesk_aps_client_id,
            self.autodesk_aps_client_secret,
        )

    @property
    def procore_configuration_complete(self) -> bool:
        return self._client_credentials_complete(
            self.procore_client_id,
            self.procore_client_secret,
        )

    @property
    def bentley_itwin_configuration_complete(self) -> bool:
        return self._client_credentials_complete(
            self.bentley_itwin_client_id,
            self.bentley_itwin_client_secret,
        )

    @property
    def trimble_configuration_complete(self) -> bool:
        return self._client_credentials_complete(
            self.trimble_client_id,
            self.trimble_client_secret,
        )

    @property
    def arcgis_configuration_complete(self) -> bool:
        return self._client_credentials_complete(
            self.arcgis_client_id,
            self.arcgis_client_secret,
        )

    @property
    def seequent_configuration_complete(self) -> bool:
        return self._client_credentials_complete(
            self.seequent_client_id,
            self.seequent_client_secret,
        )

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
            "observability": {
                "exporter": self.observability_exporter,
                "log_level": self.log_level,
                "application_insights_configured": bool(
                    self.applicationinsights_connection_string
                ),
            },
            "backend_base": _safe_origin(self.backend_base),
            "frontend_base": _safe_origin(self.frontend_base),
            "cors_origins": [_safe_origin(origin) for origin in self.cors_origin_list],
            "database_driver": self.database_driver,
            "providers": {
                "identity": self.identity_provider,
                "object_storage": self.object_storage_provider,
                "queue": self.queue_provider,
                "iot_cloud": self.iot_cloud_provider,
                "processing": self.processing_provider,
                "weather": self.weather_provider,
                "satellite": self.satellite_provider,
                "gis": self.gis_provider,
                "construction": self.construction_provider,
                "asset_management": self.asset_management_provider,
                "maritime": self.maritime_provider,
                "erp": self.erp_provider,
                "notifications": self.notification_provider,
                "report_narrative": self.report_narrative_provider,
            },
            "configured": {
                "google_oauth": bool(
                    self.google_client_id and self.google_client_secret
                ),
                "microsoft_oauth": bool(
                    self.microsoft_client_id and self.microsoft_client_secret
                ),
                "entra_external_id": self.entra_external_id_configuration_complete,
                "openai": bool(self.openai_api_key),
                "smtp": bool(
                    self.smtp_configuration_complete
                    and (not self.is_deployed or self.smtp_use_tls)
                ),
                "azure_notification_hubs": bool(
                    self.azure_notification_hubs_namespace
                    and self.azure_notification_hubs_hub_name
                    and self.azure_notification_hubs_sas_key_name
                    and self.azure_notification_hubs_sas_key
                ),
                "s3": bool(self.s3_bucket),
                "azure_blob": bool(
                    self.azure_storage_container
                    and (
                        self.azure_storage_connection_string
                        or self.azure_storage_account_url
                    )
                ),
                "azure_service_bus": bool(
                    self.service_bus_connection_string
                    or self.service_bus_fully_qualified_namespace
                ),
                "azure_app_configuration": bool(self.azure_app_configuration_endpoint),
                "azure_event_grid": bool(
                    self.azure_event_grid_enabled
                    and self.azure_event_grid_webhook_secret
                ),
                "azure_iot_hub": bool(
                    self.azure_iot_hub_enabled
                    and self.azure_iot_hub_webhook_secret
                    and self.azure_iot_hub_name
                ),
                "nodeodm": bool(
                    self.processing_provider in {"nodeodm", "opendronemap"}
                    and self.nodeodm_base_url
                ),
                "copernicus": self.satellite_provider
                in {"copernicus", "cdse", "sentinel"},
                "aemet": bool(
                    self.weather_provider in {"aemet", "aemet_opendata"}
                    and self.aemet_api_key
                ),
                "miteco": self.gis_provider == "miteco",
                "autodesk_aps": self.autodesk_aps_configuration_complete,
                "procore": self.procore_configuration_complete,
                "bentley_itwin": self.bentley_itwin_configuration_complete,
                "trimble": self.trimble_configuration_complete,
                "arcgis": self.arcgis_configuration_complete,
                "seequent": self.seequent_configuration_complete,
                # No live maritime adapter or customer entitlement is configured.
                "maritime": False,
                "erpnext": bool(
                    self.erpnext_base_url
                    and self.erpnext_api_key
                    and self.erpnext_api_secret
                ),
                "odoo": bool(
                    self.odoo_base_url and self.odoo_database and self.odoo_api_key
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
