"""Provider-neutral ERP contracts owned by GeoVision's order domain."""

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

from app.core.integration import IntegrationResult


@dataclass(frozen=True, slots=True)
class ERPWriteResult:
    """External acknowledgement without making the provider ID authoritative."""

    external_id: str
    external_model: str | None = None
    invoice_status: str | None = None
    stock_status: str | None = None
    purchase_status: str | None = None

    def __post_init__(self) -> None:
        if not self.external_id.strip():
            raise ValueError("ERP external_id must not be empty")


@dataclass(frozen=True, slots=True)
class ERPCommand:
    """Canonical write command; provider-specific models never cross this port."""

    resource_type: str
    internal_id: str
    organization_id: str | None
    source_event: str
    idempotency_key: str
    values: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.resource_type.strip() or not self.internal_id.strip():
            raise ValueError("ERP resource type and internal ID must not be empty")
        if not self.idempotency_key.strip():
            raise ValueError("ERP idempotency key must not be empty")


def as_erp_write_result(value: ERPWriteResult | str | object) -> ERPWriteResult:
    """Normalize legacy string acknowledgements during the port migration."""

    if isinstance(value, ERPWriteResult):
        return value
    if isinstance(value, str) and value.strip():
        return ERPWriteResult(external_id=value.strip())
    raise ValueError("ERP provider did not return a valid external reference")


@runtime_checkable
class ERPProvider(Protocol):
    provider_name: str

    def upsert(
        self,
        resource_type: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> IntegrationResult[ERPWriteResult | str]: ...

    def health(self) -> Mapping[str, Any]: ...


__all__ = [
    "ERPCommand",
    "ERPProvider",
    "ERPWriteResult",
    "as_erp_write_result",
]
