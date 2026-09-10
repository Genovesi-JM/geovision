"""Odoo 19 JSON-2 adapter isolated behind GeoVision's canonical ERP port."""

from __future__ import annotations

import json
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.core.integration import (
    IntegrationAuthenticationError,
    IntegrationRateLimitError,
    IntegrationTimeoutError,
    IntegrationUnavailableError,
    IntegrationValidationError,
)

from .base import ErpAdapter, ErpResult


class OdooAdapter(ErpAdapter):
    """Call one audited Odoo bridge method instead of leaking Odoo models."""

    id = "odoo"
    _SUPPORTED_RESOURCES = frozenset(
        {
            "customer",
            "product",
            "service",
            "order",
            "invoice",
            "payment",
            "delivery",
            "supplier",
            "purchase_order",
            "inventory",
        }
    )

    def __init__(
        self,
        base_url: str,
        database: str,
        api_key: str,
        *,
        bridge_model: str = "geovision.integration.bridge",
        bridge_method: str = "sync_from_geovision",
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.database = database.strip()
        self._api_key = api_key
        self.bridge_model = bridge_model.strip()
        self.bridge_method = bridge_method.strip()
        self.timeout_seconds = timeout_seconds

    def _request(self, body: dict[str, Any]) -> Any:
        path = "/json/2/{}/{}".format(
            quote(self.bridge_model, safe="."),
            quote(self.bridge_method, safe="_"),
        )
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(body, separators=(",", ":"), default=str).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"bearer {self._api_key}",
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "GeoVision-Odoo/1.0",
                "X-Odoo-Database": self.database,
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8") or "null")
        except HTTPError as exc:
            kwargs: dict[str, Any] = {
                "provider": self.id,
                "operation": "upsert",
                "code": f"http_{exc.code}",
                "message": f"Odoo returned HTTP {exc.code}",
            }
            if exc.code in {401, 403}:
                error_type = IntegrationAuthenticationError
            elif exc.code == 408:
                error_type = IntegrationTimeoutError
            elif exc.code == 429:
                error_type = IntegrationRateLimitError
                retry_after = (exc.headers or {}).get("Retry-After")
                try:
                    kwargs["retry_after_seconds"] = max(0.0, float(retry_after))
                except (TypeError, ValueError):
                    pass
            elif 500 <= exc.code <= 599:
                error_type = IntegrationUnavailableError
            else:
                error_type = IntegrationValidationError
            raise error_type(**kwargs) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise IntegrationTimeoutError(
                provider=self.id,
                operation="upsert",
                message="Odoo request timed out",
            ) from exc
        except URLError as exc:
            raise IntegrationUnavailableError(
                provider=self.id,
                operation="upsert",
                message="Odoo connection failed",
            ) from exc
        except json.JSONDecodeError as exc:
            raise IntegrationUnavailableError(
                provider=self.id,
                operation="upsert",
                message="Odoo returned an invalid response",
                retryable=True,
            ) from exc

    def upsert(
        self,
        resource_type: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> ErpResult:
        canonical_type = resource_type.strip().lower()
        if canonical_type not in self._SUPPORTED_RESOURCES:
            raise IntegrationValidationError(
                provider=self.id,
                operation="upsert",
                message="GeoVision resource type is not enabled for Odoo sync",
            )
        internal_id = str(payload.get("geovision_id") or payload.get("id") or "").strip()
        if not internal_id:
            raise IntegrationValidationError(
                provider=self.id,
                operation="upsert",
                message="GeoVision resource ID is required for Odoo sync",
            )
        response = self._request(
            {
                "context": {"tracking_disable": False},
                "resource_type": canonical_type,
                "geovision_id": internal_id,
                "organization_id": payload.get("organization_id")
                or payload.get("company_id"),
                "source_event": payload.get("source_event") or "sync.requested",
                "idempotency_key": idempotency_key,
                "values": {
                    key: value
                    for key, value in payload.items()
                    if key
                    not in {
                        "geovision_id",
                        "id",
                        "organization_id",
                        "company_id",
                        "source_event",
                    }
                },
            }
        )
        if not isinstance(response, dict) or not str(response.get("external_id") or "").strip():
            raise IntegrationUnavailableError(
                provider=self.id,
                operation="upsert",
                message="Odoo bridge did not return an external reference",
                retryable=True,
            )
        return ErpResult(
            external_id=str(response["external_id"]),
            external_model=(
                str(response["external_model"])
                if response.get("external_model") is not None
                else None
            ),
            invoice_status=_optional_text(response.get("invoice_status")),
            stock_status=_optional_text(response.get("stock_status")),
            purchase_status=_optional_text(response.get("purchase_status")),
            provider=self.id,
        )

    def health(self) -> dict[str, Any]:
        return {
            "provider": self.id,
            "configured": True,
            "mode": "live",
            "api": "json-2",
        }


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized[:100] or None


__all__ = ["OdooAdapter"]
