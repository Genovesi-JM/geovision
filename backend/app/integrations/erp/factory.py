from __future__ import annotations

from app.core.config import Settings, settings
from app.core.integration import IntegrationConfigurationError

from .base import ErpAdapter


def get_erp_adapter(
    config: Settings = settings,
    *,
    provider_name: str | None = None,
) -> ErpAdapter:
    provider_name = (provider_name or config.erp_provider).lower()
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
    if provider_name == "odoo":
        if not all((config.odoo_base_url, config.odoo_database, config.odoo_api_key)):
            raise IntegrationConfigurationError(
                provider="odoo",
                operation="initialize",
                message="Odoo is selected but its URL, database, or API key is incomplete",
            )
        from .odoo import OdooAdapter

        return OdooAdapter(
            config.odoo_base_url,
            config.odoo_database,
            config.odoo_api_key,
            bridge_model=config.odoo_bridge_model,
            bridge_method=config.odoo_bridge_method,
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
