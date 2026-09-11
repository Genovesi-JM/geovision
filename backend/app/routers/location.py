"""Authenticated, provider-neutral location-service API."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.integration import IntegrationResult, IntegrationStatus
from app.core.time import utc_now
from app.deps import get_authorization_context, get_current_user
from app.integrations.location import create_location_provider
from app.models import User
from app.modules.economics.schemas import ProviderUsageCreate
from app.modules.economics.services import record_provider_usage
from app.modules.identity.domain import AuthorizationContext
from app.modules.assets.location_ports import GeoCoordinate, LocationProvider
from app.modules.assets.location_schemas import (
    CoordinateIn,
    PlaceAutocompleteIn,
    PlaceAutocompleteOut,
    PlaceResolveIn,
    PlaceSuggestionOut,
    ResolvedPlaceOut,
    ReverseGeocodeIn,
    ReverseGeocodeOut,
    RouteComputeIn,
    RouteEstimateOut,
)


router = APIRouter(prefix="/location", tags=["location"])


def get_location_provider() -> Iterator[LocationProvider]:
    provider = create_location_provider()
    try:
        yield provider
    finally:
        close = getattr(provider, "close", None)
        if callable(close):
            close()


def _point(value: CoordinateIn) -> GeoCoordinate:
    return GeoCoordinate(latitude=value.latitude, longitude=value.longitude)


def _require_value(result: IntegrationResult):
    if result.ok and result.value is not None:
        return result.value
    code = result.failure.code if result.failure else "provider_failed"
    status_code = {
        "invalid_place_reference": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "place_not_found": status.HTTP_404_NOT_FOUND,
        "provider_rate_limited": status.HTTP_429_TOO_MANY_REQUESTS,
        "provider_timeout": status.HTTP_504_GATEWAY_TIMEOUT,
        "provider_not_configured": status.HTTP_503_SERVICE_UNAVAILABLE,
    }.get(code, status.HTTP_502_BAD_GATEWAY)
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": "Location service is unavailable"},
    )


def _record_usage(
    db: Session,
    *,
    result: IntegrationResult,
    context: AuthorizationContext,
    actor: User,
    service: str,
) -> None:
    if (
        result.status is not IntegrationStatus.SUCCEEDED
        or not context.active_organization_id
    ):
        return
    usage_id = str(uuid.uuid4())
    record_provider_usage(
        db,
        payload=ProviderUsageCreate(
            organization_id=context.active_organization_id,
            workspace_id=context.active_workspace_id,
            provider=result.provider,
            service=service,
            usage_type="provider_request",
            quantity=Decimal("1"),
            unit="request",
            occurred_at=utc_now(),
            idempotency_key=f"location:{usage_id}:{result.operation}",
            metadata={"operation": result.operation},
        ),
        actor=actor,
    )
    db.commit()


@router.get("/capabilities")
def capabilities(
    user: User = Depends(get_current_user),
    provider: LocationProvider = Depends(get_location_provider),
):
    del user
    configured = bool(getattr(provider, "configured", True))
    return {
        "provider": provider.provider_name,
        "configured": configured,
        "capabilities": {
            "autocomplete": configured,
            "place_resolution": configured,
            "reverse_geocoding": configured,
            "driving_route_estimate": configured,
        },
    }


@router.post("/places:autocomplete", response_model=PlaceAutocompleteOut)
def autocomplete(
    body: PlaceAutocompleteIn,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
    provider: LocationProvider = Depends(get_location_provider),
):
    result = provider.autocomplete(
        query=body.query.strip(),
        session_token=body.session_token,
        language_code=body.language_code,
        region_code=body.region_code,
        bias=_point(body.bias) if body.bias else None,
    )
    suggestions = _require_value(result)
    _record_usage(
        db,
        result=result,
        context=context,
        actor=user,
        service="places_autocomplete",
    )
    return PlaceAutocompleteOut(
        provider=result.provider,
        simulated=result.status is IntegrationStatus.SIMULATED,
        suggestions=[
            PlaceSuggestionOut(
                provider_reference=item.provider_reference,
                primary_text=item.primary_text,
                secondary_text=item.secondary_text,
            )
            for item in suggestions
        ],
    )


@router.post("/places:resolve", response_model=ResolvedPlaceOut)
def resolve_place(
    body: PlaceResolveIn,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
    provider: LocationProvider = Depends(get_location_provider),
):
    result = provider.resolve_place(
        provider_reference=body.provider_reference,
        session_token=body.session_token,
        language_code=body.language_code,
    )
    place = _require_value(result)
    _record_usage(
        db,
        result=result,
        context=context,
        actor=user,
        service="place_details",
    )
    return ResolvedPlaceOut(
        provider=result.provider,
        simulated=result.status is IntegrationStatus.SIMULATED,
        provider_reference=place.provider_reference,
        display_name=place.display_name,
        formatted_address=place.formatted_address,
        coordinate=CoordinateIn(
            latitude=place.coordinate.latitude,
            longitude=place.coordinate.longitude,
        ),
    )


@router.post("/routes:compute", response_model=RouteEstimateOut)
def compute_route(
    body: RouteComputeIn,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
    provider: LocationProvider = Depends(get_location_provider),
):
    result = provider.compute_route(
        origin=_point(body.origin),
        destination=_point(body.destination),
        language_code=body.language_code,
    )
    route = _require_value(result)
    _record_usage(
        db,
        result=result,
        context=context,
        actor=user,
        service="routes_compute",
    )
    return RouteEstimateOut(
        provider=result.provider,
        simulated=result.status is IntegrationStatus.SIMULATED,
        distance_meters=route.distance_meters,
        duration_seconds=route.duration_seconds,
        encoded_polyline=route.encoded_polyline,
        traffic_aware=route.traffic_aware,
    )


@router.post("/addresses:reverse", response_model=ReverseGeocodeOut)
def reverse_geocode(
    body: ReverseGeocodeIn,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
    provider: LocationProvider = Depends(get_location_provider),
):
    result = provider.reverse_geocode(
        coordinate=_point(body.coordinate),
        language_code=body.language_code,
        region_code=body.region_code,
    )
    address = _require_value(result)
    _record_usage(
        db,
        result=result,
        context=context,
        actor=user,
        service="geocoding_reverse",
    )
    return ReverseGeocodeOut(
        provider=result.provider,
        simulated=result.status is IntegrationStatus.SIMULATED,
        provider_reference=address.provider_reference,
        formatted_address=address.formatted_address,
        coordinate=CoordinateIn(
            latitude=address.coordinate.latitude,
            longitude=address.coordinate.longitude,
        ),
        granularity=address.granularity,
    )


__all__ = ["get_location_provider", "router"]
