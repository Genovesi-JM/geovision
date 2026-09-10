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


class ErpNextAdapter(ErpAdapter):
    id = "erpnext"
    _DOCUMENT_TYPES = {
        "customer": "Customer",
        "product": "Item",
        "service": "Item",
        "order": "Sales Order",
        "invoice": "Sales Invoice",
        "payment": "Payment Entry",
        "delivery": "Delivery Note",
        "supplier": "Supplier",
        "purchase_order": "Purchase Order",
        "inventory": "Stock Entry",
    }

    def __init__(
        self,
        base_url: str,
        api_key: str,
        api_secret: str,
        timeout_seconds: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self._authorization = f"token {api_key}:{api_secret}"
        self.timeout_seconds = timeout_seconds

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        operation_is_read_only = method.upper() in {"GET", "HEAD", "OPTIONS"}
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"Authorization": self._authorization, "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode() or "{}")
        except HTTPError as exc:
            # Never include request headers or credentials in application logs.
            error_kwargs: dict[str, Any] = {
                "provider": self.id,
                "operation": method.lower(),
                "code": f"http_{exc.code}",
                "message": f"ERPNext returned HTTP {exc.code}",
            }
            if exc.code in {401, 403}:
                error_type = IntegrationAuthenticationError
            elif exc.code == 408:
                error_type = IntegrationTimeoutError
                error_kwargs["retryable"] = operation_is_read_only
            elif exc.code == 429:
                error_type = IntegrationRateLimitError
                error_kwargs["retryable"] = operation_is_read_only
                retry_after = (exc.headers or {}).get("Retry-After")
                try:
                    parsed_retry_after = float(retry_after)
                    if parsed_retry_after >= 0:
                        error_kwargs["retry_after_seconds"] = parsed_retry_after
                except (TypeError, ValueError):
                    pass
            elif 500 <= exc.code <= 599:
                error_type = IntegrationUnavailableError
                error_kwargs["retryable"] = operation_is_read_only
            else:
                error_type = IntegrationValidationError
            raise error_type(
                **error_kwargs,
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise IntegrationTimeoutError(
                provider=self.id,
                operation=method.lower(),
                message="ERPNext request timed out",
                retryable=operation_is_read_only,
            ) from exc
        except URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise IntegrationTimeoutError(
                    provider=self.id,
                    operation=method.lower(),
                    message="ERPNext request timed out",
                    retryable=operation_is_read_only,
                ) from exc
            raise IntegrationUnavailableError(
                provider=self.id,
                operation=method.lower(),
                message="ERPNext connection failed",
                retryable=operation_is_read_only,
            ) from exc
        except Exception as exc:
            raise IntegrationUnavailableError(
                provider=self.id,
                operation=method.lower(),
                message="ERPNext returned an invalid response",
                retryable=operation_is_read_only,
            ) from exc

    def upsert(self, resource_type: str, payload: dict[str, Any], idempotency_key: str) -> ErpResult:
        # GeoVision's key is stored in a custom field when that field exists in
        # ERPNext. A lost POST response is terminal for automatic processing:
        # the custom field is not assumed unique until operators configure and
        # verify provider-side reconciliation/deduplication.
        body = dict(payload)
        body.setdefault("custom_geovision_idempotency_key", idempotency_key)
        document_type = self._DOCUMENT_TYPES.get(resource_type, resource_type)
        result = self._request("POST", f"/api/resource/{quote(document_type)}", body)
        data = result.get("data") or {}
        external_id = str(data.get("name") or data.get("id") or "accepted")
        return ErpResult(
            external_id=external_id,
            external_model=document_type,
            provider=self.id,
        )

    def health(self) -> dict[str, Any]:
        return {"provider": self.id, "configured": True, "mode": "live"}
