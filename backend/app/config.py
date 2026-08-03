import secrets
import warnings
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional

_INSECURE_DEFAULT = "CHANGE_ME"

class Settings(BaseSettings):
    app_name: str = "GeoVision Backend"
    env: str = "dev"

    # JWT / Auth — MUST be set via SECRET_KEY env var in production
    secret_key: str = _INSECURE_DEFAULT
    algorithm: str = "HS256"
    access_token_expires_minutes: int = 60

    # Frontend URL used to build password-reset links (no trailing slash)
    frontend_base: str = "http://127.0.0.1:8001"

    # Optional SMTP settings for sending password reset emails
    smtp_host: Optional[str] = None
    smtp_port: int = 25
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_use_tls: bool = True

    # Backend base URL used for OAuth callbacks (no trailing slash)
    backend_base: str = "http://127.0.0.1:8010"

    # Google OAuth settings (optional)
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None

    # Microsoft OAuth / Entra ID settings (optional)
    microsoft_client_id: Optional[str] = None
    microsoft_client_secret: Optional[str] = None
    microsoft_tenant_id: str = "common"  # "common" for multi-tenant, or specific tenant ID

    # Refresh token settings
    refresh_token_expires_days: int = 30

    # Encryption key for sensitive data at rest (API keys, connector tokens)
    encryption_key: Optional[str] = None  # Fernet key, generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

    # Bases de dados
    database_url: str = "sqlite:///./geovision.db"
    accounts_database_url: str = "sqlite:///./accounts.db"
    
    @field_validator("database_url", mode="before")
    @classmethod
    def fix_postgres_url(cls, v: str) -> str:
        """Some providers use postgres:// but SQLAlchemy 2.0 requires postgresql://"""
        if v and v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql://", 1)
        return v

    # OpenAI (opcional – para o chatbot AI)
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"

    # ERP integration. GeoVision remains the customer-facing source of truth;
    # ERPNext receives commercial/accounting documents through an outbox.
    erp_provider: str = "mock"
    erpnext_base_url: Optional[str] = None
    erpnext_api_key: Optional[str] = None
    erpnext_api_secret: Optional[str] = None
    erpnext_webhook_secret: Optional[str] = None

    # IoT bridge. MQTT is opt-in so tests and ordinary web development do not
    # require a broker. REST ingestion and simulators remain available.
    mqtt_enabled: bool = False
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None
    mqtt_tls: bool = False
    mqtt_topic_prefix: str = "geovision"
    mqtt_client_id: str = "geovision-backend"
    iot_message_max_age_seconds: int = 300
    iot_offline_after_seconds: int = 120
    iot_command_ttl_seconds: int = 300
    iot_max_messages_per_minute: int = 120
    iot_raw_retention_days: int = 30
    iot_aggregate_retention_days: int = 730

    # Pydantic v2 settings: accept extra env vars (ignore unknown variables)
    model_config = {
        "env_file": Path(__file__).resolve().parent.parent / ".env",
        "extra": "ignore",
    }

settings = Settings()

# ── Secret key safety check ──────────────────────────────────────
if settings.secret_key == _INSECURE_DEFAULT:
    if settings.env in ("production", "prod"):
        raise RuntimeError(
            "FATAL: SECRET_KEY env var is not set. "
            "Refusing to start in production with the insecure default."
        )
    # Dev / test: auto-generate a random key so tokens still work
    _generated = secrets.token_urlsafe(48)
    warnings.warn(
        "SECRET_KEY not set — using a random ephemeral key. "
        "Set SECRET_KEY env var before deploying to production.",
        stacklevel=1,
    )
    settings.secret_key = _generated

if settings.env in ("production", "prod") and settings.mqtt_enabled and not settings.encryption_key:
    raise RuntimeError("FATAL: ENCRYPTION_KEY is required when MQTT is enabled in production")

# Backwards-compatible names expected elsewhere in the codebase
JWT_SECRET = settings.secret_key
JWT_ALG = settings.algorithm
JWT_EXPIRE_MIN = settings.access_token_expires_minutes

# Expose OpenAI key alias for modules that look for OPENAI_API_KEY
OPENAI_API_KEY = settings.openai_api_key
# Backwards-compatible DB URL constant for alembic/env.py
DATABASE_URL = settings.database_url
