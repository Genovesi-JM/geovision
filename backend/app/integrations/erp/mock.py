from __future__ import annotations

import hashlib
from typing import Any

from .base import ErpAdapter, ErpResult


class MockErpAdapter(ErpAdapter):
    id = "mock"

    def upsert(self, document_type: str, payload: dict[str, Any], idempotency_key: str) -> ErpResult:
        digest = hashlib.sha256(idempotency_key.encode()).hexdigest()[:12]
        return ErpResult(external_id=f"MOCK-{document_type.upper()}-{digest}")

    def health(self) -> dict[str, Any]:
        return {"provider": self.id, "configured": True, "mode": "simulation"}
