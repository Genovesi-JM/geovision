from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .base import ErpAdapter, ErpResult


class ErpNextAdapter(ErpAdapter):
    id = "erpnext"

    def __init__(self, base_url: str, api_key: str, api_secret: str):
        self.base_url = base_url.rstrip("/")
        self._authorization = f"token {api_key}:{api_secret}"

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"Authorization": self._authorization, "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode() or "{}")
        except HTTPError as exc:
            # Never include request headers or credentials in application logs.
            detail = exc.read().decode(errors="replace")[:500]
            raise RuntimeError(f"ERPNext returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"ERPNext connection failed: {exc.reason}") from exc

    def upsert(self, document_type: str, payload: dict[str, Any], idempotency_key: str) -> ErpResult:
        # GeoVision's key is stored in a custom field when that field exists in
        # ERPNext. The durable local outbox remains the primary dedupe guard.
        body = dict(payload)
        body.setdefault("custom_geovision_idempotency_key", idempotency_key)
        result = self._request("POST", f"/api/resource/{quote(document_type)}", body)
        data = result.get("data") or {}
        external_id = str(data.get("name") or data.get("id") or "accepted")
        return ErpResult(external_id=external_id)

    def health(self) -> dict[str, Any]:
        return {"provider": self.id, "configured": True, "mode": "live"}
