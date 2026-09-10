"""Contract-test GIS adapter with deterministic opaque layer references."""

from __future__ import annotations

import uuid
from typing import Any, Mapping

from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    IntegrationStatus,
)
from app.core.references import ExternalReference
from app.modules.assets.ports import GISLayerQuery, GISLayerResult


class FakeGISProvider:
    """Return fixture layer capabilities, never inferred geospatial measurements."""

    provider_name = "fake"
    adapter_version = "geovision-gis-contract-fixture-v1"

    def query_layers(
        self,
        request: GISLayerQuery | Mapping[str, Any],
    ) -> IntegrationResult[GISLayerResult | Mapping[str, Any]]:
        operation = "query_layers"
        try:
            raw_internal_id = (
                request.internal_id
                if isinstance(request, GISLayerQuery)
                else request["internal_id"]
            )
            internal_id = uuid.UUID(str(raw_internal_id))
        except (KeyError, TypeError, ValueError):
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation=operation,
                failure=IntegrationFailure(
                    code="invalid_request",
                    message="GIS fixture requires a GeoVision internal_id UUID",
                ),
            )
        provider_reference = "fixture-layer-set-" + str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"geovision:gis:{internal_id}")
        )
        return IntegrationResult(
            provider=self.provider_name,
            operation=operation,
            status=IntegrationStatus.SIMULATED,
            value={
                "layers": (
                    {
                        "name": "fixture_project_boundary",
                        "kind": "vector",
                        "crs": "EPSG:4326",
                    },
                ),
                "measurements_authoritative": False,
            },
            external_reference=ExternalReference(
                internal_id=internal_id,
                provider=self.provider_name,
                resource_type="gis_layer_collection",
                value=provider_reference,
            ),
        )


__all__ = ["FakeGISProvider"]
