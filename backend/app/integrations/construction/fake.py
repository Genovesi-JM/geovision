"""Contract-test construction adapter with deterministic opaque references."""

from __future__ import annotations

import uuid
from typing import Any, Mapping

from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    IntegrationStatus,
)
from app.core.references import ExternalReference


class FakeConstructionProvider:
    """Exercise the port without simulating vendor connectivity or measurements."""

    provider_name = "fake"
    adapter_version = "geovision-construction-contract-fixture-v1"

    def synchronize_project(
        self,
        request: Mapping[str, Any],
        *,
        idempotency_key: str,
    ) -> IntegrationResult[Mapping[str, Any]]:
        operation = "synchronize_project"
        try:
            internal_id = uuid.UUID(str(request["internal_id"]))
        except (KeyError, TypeError, ValueError):
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation=operation,
                failure=IntegrationFailure(
                    code="invalid_request",
                    message="Construction fixture requires a GeoVision internal_id UUID",
                ),
            )
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation=operation,
                failure=IntegrationFailure(
                    code="invalid_request",
                    message="Construction synchronization requires an idempotency key",
                ),
            )
        normalized_key = idempotency_key.strip()
        provider_reference = "fixture-project-" + str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"geovision:{internal_id}:{normalized_key}",
            )
        )
        return IntegrationResult(
            provider=self.provider_name,
            operation=operation,
            status=IntegrationStatus.SIMULATED,
            value={
                "synchronized": True,
                "source": "contract_fixture",
            },
            external_reference=ExternalReference(
                internal_id=internal_id,
                provider=self.provider_name,
                resource_type="construction_project",
                value=provider_reference,
            ),
        )


__all__ = ["FakeConstructionProvider"]
