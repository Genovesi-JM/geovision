from __future__ import annotations

from app.core.config import Settings, settings
from app.core.integration import IntegrationConfigurationError

from .base import ErpAdapter


def get_erp_adapter(config: Settings = settings) -> ErpAdapter:
    provider_name = config.erp_provider.lower()
    if provider_name == "erpnext":
        if not all(
            (
                config.erpnext_base_url,
                config.erpnext_api_key,
                config.erpnext_api_secret,
            )
        ):
            raise IntegrationConfigurationError(
                provider="erpnext",
                operation="initialize",
                message="ERPNext is selected but its URL/API credentials are incomplete",
            )
        from .erpnext import ErpNextAdapter

        return ErpNextAdapter(
            config.erpnext_base_url,
            config.erpnext_api_key,
            config.erpnext_api_secret,
            timeout_seconds=config.integration_read_timeout_seconds,
        )
    if provider_name == "mock":
        if config.is_deployed:
            raise IntegrationConfigurationError(
                provider="mock",
                operation="initialize",
                message="mock ERP is not allowed in staging or production",
            )
        from .mock import MockErpAdapter

        return MockErpAdapter()
    raise IntegrationConfigurationError(
        provider=provider_name or "erp",
        operation="initialize",
        message="unsupported ERP provider",
    )
