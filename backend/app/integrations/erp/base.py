from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.core.integration import IntegrationResult, IntegrationStatus


@dataclass(frozen=True, slots=True, init=False)
class ErpResult(IntegrationResult[str]):
    """Normalized ERP result with the legacy ``external_id`` accessor."""

    def __init__(
        self,
        external_id: str,
        status: str = "accepted",
        provider: str = "erp",
    ) -> None:
        normalized_status = IntegrationStatus(status)
        IntegrationResult.__init__(
            self,
            provider=provider,
            operation="upsert",
            status=normalized_status,
            value=external_id,
        )

    @property
    def external_id(self) -> str:
        return self.value or ""


class ErpAdapter(ABC):
    id: str

    @property
    def provider_name(self) -> str:
        return self.id

    @abstractmethod
    def upsert(
        self,
        document_type: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> IntegrationResult[str]:
        """Create/update one ERP document without duplicating retried events."""

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Return a secret-free provider readiness summary."""
