from __future__ import annotations

from app.config import settings

from .base import ErpAdapter
from .erpnext import ErpNextAdapter
from .mock import MockErpAdapter


def get_erp_adapter() -> ErpAdapter:
    if settings.erp_provider.lower() == "erpnext":
        if not all((settings.erpnext_base_url, settings.erpnext_api_key, settings.erpnext_api_secret)):
            raise RuntimeError("ERPNext is selected but its URL/API credentials are incomplete")
        return ErpNextAdapter(
            settings.erpnext_base_url,
            settings.erpnext_api_key,
            settings.erpnext_api_secret,
        )
    return MockErpAdapter()
