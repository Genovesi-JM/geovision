from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.core.integration import IntegrationResult, IntegrationStatus
from app.modules.orders.ports import ERPWriteResult


@dataclass(frozen=True, slots=True, init=False)
class ErpResult(IntegrationResult[ERPWriteResult]):
    """Normalized ERP result with the legacy ``external_id`` accessor."""

    def __init__(
        self,
        external_id: str,
        status: str = "accepted",
        provider: str = "erp",
        external_model: str | None = None,
        invoice_status: str | None = None,
        stock_status: str | None = None,
        purchase_status: str | None = None,
    ) -> None:
        normalized_status = IntegrationStatus(status)
        IntegrationResult.__init__(
            self,
            provider=provider,
            operation="upsert",
            status=normalized_status,
            value=ERPWriteResult(
                external_id=external_id,
                external_model=external_model,
                invoice_status=invoice_status,
                stock_status=stock_status,
                purchase_status=purchase_status,
            ),
        )

    @property
    def external_id(self) -> str:
        return self.value.external_id if self.value else ""


class ErpAdapter(ABC):
    id: str

    @property
    def provider_name(self) -> str:
        return self.id

    @abstractmethod
    def upsert(
        self,
        resource_type: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> IntegrationResult[ERPWriteResult | str]:
        """Create/update one ERP document without duplicating retried events."""

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Return a secret-free provider readiness summary."""
