from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ErpResult:
    external_id: str
    status: str = "accepted"


class ErpAdapter(ABC):
    id: str

    @abstractmethod
    def upsert(self, document_type: str, payload: dict[str, Any], idempotency_key: str) -> ErpResult:
        """Create/update one ERP document without duplicating retried events."""

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Return a secret-free provider readiness summary."""
