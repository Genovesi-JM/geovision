"""External-system ports owned by the assets domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable
from uuid import UUID

from app.core.integration import IntegrationResult


@dataclass(frozen=True, slots=True)
class AssetSynchronizationRequest:
    """Provider-neutral asset handoff tied to a GeoVision UUID."""

    internal_id: UUID
    asset_kind: str
    external_reference: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AssetSynchronizationReceipt:
    """Asset-sync acknowledgement without operational or analytic claims."""

    synchronized: bool
    source: str
    measurements_authoritative: bool = False
    diagnostic_authority: bool = False
    context_only: bool = True


@dataclass(frozen=True, slots=True)
class GISLayerQuery:
    """Bounded spatial query tied to an authoritative GeoVision resource."""

    internal_id: UUID
    collection_key: str
    bbox: tuple[float, float, float, float]
    limit: int = 25
    crs: str = "OGC:CRS84"


@dataclass(frozen=True, slots=True)
class GISFeatureDescriptor:
    """Provider feature retained as context, never as a GeoVision identity."""

    provider_reference: str
    geometry: Mapping[str, Any] | None
    properties: Mapping[str, Any]
    bbox: tuple[float, ...]
    provenance: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class GISLayerResult:
    """Normalized GIS context with explicit authority limitations."""

    collection_key: str
    provider_collection_id: str
    title: str
    features: tuple[GISFeatureDescriptor, ...]
    bbox: tuple[float, float, float, float]
    crs: str
    provenance: Mapping[str, Any]
    measurements_authoritative: bool = False
    diagnostic_authority: bool = False
    context_only: bool = True


@runtime_checkable
class GISProvider(Protocol):
    provider_name: str

    def query_layers(
        self,
        request: GISLayerQuery | Mapping[str, Any],
    ) -> IntegrationResult[GISLayerResult | Mapping[str, Any]]: ...


@runtime_checkable
class AssetManagementProvider(Protocol):
    provider_name: str

    def synchronize_asset(
        self,
        request: AssetSynchronizationRequest | Mapping[str, Any],
        *,
        idempotency_key: str,
    ) -> IntegrationResult[AssetSynchronizationReceipt | Mapping[str, Any]]: ...


__all__ = [
    "AssetManagementProvider",
    "AssetSynchronizationReceipt",
    "AssetSynchronizationRequest",
    "GISFeatureDescriptor",
    "GISLayerQuery",
    "GISLayerResult",
    "GISProvider",
]
