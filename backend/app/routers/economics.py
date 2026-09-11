"""Private finance and provider-metering transport boundary."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.deps import get_db
from app.modules.economics.auth import EconomicsRecorder, EconomicsViewer
from app.modules.economics.domain import EconomicsError
from app.modules.economics.schemas import (
    InternalCostCreate,
    InternalCostListOut,
    InternalCostOut,
    ProviderUsageCreate,
    ProviderUsageListOut,
    ProviderUsageOut,
    ProviderUsageSummaryOut,
    UnitEconomicsOut,
)
from app.modules.economics.services import (
    catalog_item_economics,
    internal_cost_out,
    list_internal_costs,
    list_provider_usage,
    location_provider_usage_summary,
    order_economics,
    organization_economics,
    provider_usage_out,
    record_internal_cost,
    record_provider_usage,
)


router = APIRouter(prefix="/internal/economics", tags=["internal-economics"])


def _raise_domain(exc: EconomicsError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    ) from exc


@router.post(
    "/provider-usage",
    response_model=ProviderUsageOut,
    status_code=status.HTTP_201_CREATED,
)
def create_provider_usage(
    payload: ProviderUsageCreate,
    actor: EconomicsRecorder,
    db: Session = Depends(get_db),
) -> ProviderUsageOut:
    try:
        row, _created = record_provider_usage(db, payload=payload, actor=actor)
        db.commit()
        db.refresh(row)
    except EconomicsError as exc:
        db.rollback()
        _raise_domain(exc)
    except IntegrityError as exc:
        db.rollback()
        try:
            row, created = record_provider_usage(db, payload=payload, actor=actor)
            if created:
                raise exc
        except EconomicsError as domain_exc:
            db.rollback()
            _raise_domain(domain_exc)
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "economics_write_conflict",
                    "message": "The provider-usage record conflicts with an existing write",
                },
            ) from exc
    return provider_usage_out(row)


@router.get("/provider-usage", response_model=ProviderUsageListOut)
def get_provider_usage(
    _actor: EconomicsViewer,
    organization_id: str = Query(min_length=1, max_length=36),
    workspace_id: str | None = Query(default=None, max_length=36),
    order_id: str | None = Query(default=None, max_length=36),
    catalog_item_id: str | None = Query(default=None, max_length=50),
    provider: str | None = Query(default=None, min_length=1, max_length=80),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ProviderUsageListOut:
    try:
        rows, total = list_provider_usage(
            db,
            organization_id=organization_id,
            workspace_id=workspace_id,
            order_id=order_id,
            catalog_item_id=catalog_item_id,
            provider=provider,
            limit=limit,
            offset=offset,
        )
    except EconomicsError as exc:
        _raise_domain(exc)
    return ProviderUsageListOut(
        items=[provider_usage_out(row) for row in rows], total=total
    )


@router.get("/location-usage/summary", response_model=ProviderUsageSummaryOut)
def get_location_usage_summary(
    _actor: EconomicsViewer,
    organization_id: str | None = Query(default=None, min_length=1, max_length=36),
    workspace_id: str | None = Query(default=None, max_length=36),
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> ProviderUsageSummaryOut:
    try:
        return location_provider_usage_summary(
            db,
            organization_id=organization_id,
            workspace_id=workspace_id,
            since=utc_now() - timedelta(days=days),
        )
    except EconomicsError as exc:
        _raise_domain(exc)


@router.post(
    "/costs",
    response_model=InternalCostOut,
    status_code=status.HTTP_201_CREATED,
)
def create_internal_cost(
    payload: InternalCostCreate,
    actor: EconomicsRecorder,
    db: Session = Depends(get_db),
) -> InternalCostOut:
    try:
        row, _created = record_internal_cost(db, payload=payload, actor=actor)
        db.commit()
        db.refresh(row)
    except EconomicsError as exc:
        db.rollback()
        _raise_domain(exc)
    except IntegrityError as exc:
        db.rollback()
        try:
            row, created = record_internal_cost(db, payload=payload, actor=actor)
            if created:
                raise exc
        except EconomicsError as domain_exc:
            db.rollback()
            _raise_domain(domain_exc)
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "economics_write_conflict",
                    "message": "The direct-cost record conflicts with an existing write",
                },
            ) from exc
    return internal_cost_out(row)


@router.get("/costs", response_model=InternalCostListOut)
def get_internal_costs(
    _actor: EconomicsViewer,
    organization_id: str = Query(min_length=1, max_length=36),
    workspace_id: str | None = Query(default=None, max_length=36),
    order_id: str | None = Query(default=None, max_length=36),
    catalog_item_id: str | None = Query(default=None, max_length=50),
    cost_type: str | None = Query(default=None, min_length=2, max_length=40),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> InternalCostListOut:
    try:
        rows, total = list_internal_costs(
            db,
            organization_id=organization_id,
            workspace_id=workspace_id,
            order_id=order_id,
            catalog_item_id=catalog_item_id,
            cost_type=cost_type,
            limit=limit,
            offset=offset,
        )
    except EconomicsError as exc:
        _raise_domain(exc)
    return InternalCostListOut(
        items=[internal_cost_out(row) for row in rows], total=total
    )


@router.get("/orders/{order_id}", response_model=UnitEconomicsOut)
def get_order_economics(
    order_id: str,
    _actor: EconomicsViewer,
    db: Session = Depends(get_db),
) -> UnitEconomicsOut:
    try:
        return order_economics(db, order_id)
    except EconomicsError as exc:
        _raise_domain(exc)


@router.get("/catalog-items/{catalog_item_id}", response_model=UnitEconomicsOut)
def get_catalog_item_economics(
    catalog_item_id: str,
    _actor: EconomicsViewer,
    db: Session = Depends(get_db),
) -> UnitEconomicsOut:
    try:
        return catalog_item_economics(db, catalog_item_id)
    except EconomicsError as exc:
        _raise_domain(exc)


@router.get("/organizations/{organization_id}", response_model=UnitEconomicsOut)
def get_organization_economics(
    organization_id: str,
    _actor: EconomicsViewer,
    db: Session = Depends(get_db),
) -> UnitEconomicsOut:
    try:
        return organization_economics(db, organization_id)
    except EconomicsError as exc:
        _raise_domain(exc)


__all__ = ["router"]
