"""Fail-closed location provider."""

from __future__ import annotations

from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    IntegrationStatus,
)
from app.modules.assets.location_ports import (
    GeoCoordinate,
    PlaceSuggestion,
    ResolvedPlace,
    RouteEstimate,
)


class UnavailableLocationProvider:
    configured = False

    def __init__(self, provider_name: str, reason: str) -> None:
        self.provider_name = provider_name
        self.reason = reason

    def _failure(self, operation: str):
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation=operation,
            status=IntegrationStatus.NOT_CONFIGURED,
            failure=IntegrationFailure(
                code="provider_not_configured",
                message=self.reason,
            ),
        )

    def autocomplete(
        self,
        *,
        query: str,
        session_token: str,
        language_code: str,
        region_code: str | None = None,
        bias: GeoCoordinate | None = None,
    ) -> IntegrationResult[tuple[PlaceSuggestion, ...]]:
        del query, session_token, language_code, region_code, bias
        return self._failure("autocomplete")

    def resolve_place(
        self,
        *,
        provider_reference: str,
        session_token: str,
        language_code: str,
    ) -> IntegrationResult[ResolvedPlace]:
        del provider_reference, session_token, language_code
        return self._failure("resolve_place")

    def compute_route(
        self,
        *,
        origin: GeoCoordinate,
        destination: GeoCoordinate,
        language_code: str,
    ) -> IntegrationResult[RouteEstimate]:
        del origin, destination, language_code
        return self._failure("compute_route")


__all__ = ["UnavailableLocationProvider"]
