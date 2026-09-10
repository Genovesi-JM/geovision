"""Deterministic contract fake for asset-management handoffs."""

from __future__ import annotations

import re
from typing import Any, Mapping
import uuid

from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    IntegrationStatus,
)
from app.core.references import ExternalReference
from app.modules.assets.ports import (
    AssetSynchronizationReceipt,
    AssetSynchronizationRequest,
)


_ASSET_KIND = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,79}$")
_MAX_IDEMPOTENCY_KEY_LENGTH = 200


class FakeAssetManagementProvider:
    """Exercise synchronization without simulating enterprise-system truth."""

    provider_name = "fake"
    adapter_version = "geovision-asset-management-contract-fixture-v1"

    @staticmethod
    def _request(
        request: AssetSynchronizationRequest | Mapping[str, Any],
    ) -> tuple[uuid.UUID, str]:
        if isinstance(request, AssetSynchronizationRequest):
            raw_internal_id: Any = request.internal_id
            raw_asset_kind: Any = request.asset_kind
        elif isinstance(request, Mapping):
            raw_internal_id = request.get("internal_id")
            raw_asset_kind = request.get("asset_kind", "ASSET")
        else:
            raise ValueError(
                "asset synchronization requires a typed request or mapping"
            )
        try:
            internal_id = uuid.UUID(str(raw_internal_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError(
                "asset synchronization requires a GeoVision internal_id UUID"
            ) from exc
        if not isinstance(raw_asset_kind, str) or not _ASSET_KIND.fullmatch(
            raw_asset_kind.strip()
        ):
            raise ValueError("asset synchronization requires a stable asset kind")
        return internal_id, raw_asset_kind.strip().upper()

    def synchronize_asset(
        self,
        request: AssetSynchronizationRequest | Mapping[str, Any],
        *,
        idempotency_key: str,
    ) -> IntegrationResult[AssetSynchronizationReceipt | Mapping[str, Any]]:
        operation = "synchronize_asset"
        try:
            internal_id, asset_kind = self._request(request)
        except (TypeError, ValueError) as exc:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation=operation,
                failure=IntegrationFailure(
                    code="invalid_request",
                    message=str(exc),
                ),
            )
        if (
            not isinstance(idempotency_key, str)
            or not idempotency_key.strip()
            or len(idempotency_key.strip()) > _MAX_IDEMPOTENCY_KEY_LENGTH
            or any(ord(character) < 32 for character in idempotency_key)
        ):
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation=operation,
                failure=IntegrationFailure(
                    code="invalid_request",
                    message=(
                        "asset synchronization requires a bounded idempotency key"
                    ),
                ),
            )
        normalized_key = idempotency_key.strip()
        provider_reference = "fixture-managed-asset-" + str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                (
                    "geovision:asset-management:"
                    f"{internal_id}:{asset_kind}:{normalized_key}"
                ),
            )
        )
        return IntegrationResult(
            provider=self.provider_name,
            operation=operation,
            status=IntegrationStatus.SIMULATED,
            value=AssetSynchronizationReceipt(
                synchronized=True,
                source="contract_fixture",
            ),
            external_reference=ExternalReference(
                internal_id=internal_id,
                provider=self.provider_name,
                resource_type="asset_management_asset",
                value=provider_reference,
            ),
        )


__all__ = ["FakeAssetManagementProvider"]
