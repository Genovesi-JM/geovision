from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional

class Settings(BaseSettings):
    app_name: str = "GeoVision Backend"
    env: str = "dev"

    # JWT / Auth
    secret_key: str = "CHANGE_ME"
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
        """Render uses postgres:// but SQLAlchemy 2.0 requires postgresql://"""
        if v and v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql://", 1)
        return v

    # OpenAI (opcional – para o chatbot AI)
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4.1-mini"

    # Pydantic v2 settings: accept extra env vars (ignore unknown variables)
    model_config = {
        "env_file": Path(__file__).resolve().parent.parent / ".env",
        "extra": "ignore",
    }

settings = Settings()

# Backwards-compatible names expected elsewhere in the codebase
JWT_SECRET = settings.secret_key
JWT_ALG = settings.algorithm
JWT_EXPIRE_MIN = settings.access_token_expires_minutes

# Expose OpenAI key alias for modules that look for OPENAI_API_KEY
OPENAI_API_KEY = settings.openai_api_key
# Backwards-compatible DB URL constant for alembic/env.py
DATABASE_URL = settings.database_url
