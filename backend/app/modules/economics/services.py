"""Persistence and calculation services for private GeoVision economics."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import hashlib
import json
import uuid
from typing import Any, Iterable

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models import (
    Account,
    Acquisition,
    Asset,
    CatalogItem,
    Company,
    ContractorAssignment,
    Dataset,
    FulfilmentJob,
    IntelligenceAcquisition,
    InternalCost,
    Notification,
    NotificationDelivery,
    Order,
    OrderItem,
    ProcessingJob,
    ProviderUsage,
    Report,
    User,
)
from app.modules.audit.services import record_audit_event

from .domain import EconomicsError, EconomicsScopeType, sanitize_metadata
from .schemas import (
    CostBreakdownOut,
    EconomicsCurrencySummaryOut,
    InternalCostCreate,
    InternalCostOut,
    ProviderUsageCreate,
    ProviderUsageOut,
    ProviderUsageSummaryItemOut,
    ProviderUsageSummaryOut,
    UnitEconomicsOut,
)


_MONEY = Decimal("0.0001")
_PERCENT = Decimal("0.01")
_NON_REVENUE_STATES = frozenset({"DRAFT", "QUOTED", "CANCELLED", "FAILED"})
_NON_REVENUE_PAYMENTS = frozenset({"CANCELLED", "REFUNDED"})


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )


def _decoded(value: str | None) -> dict[str, Any]:
    try:
        loaded = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _request_hash(payload: ProviderUsageCreate | InternalCostCreate) -> str:
    canonical = payload.model_dump(mode="json", exclude={"idempotency_key"})
    return hashlib.sha256(_json(canonical).encode("utf-8")).hexdigest()


def _invalid_reference() -> EconomicsError:
    return EconomicsError(
        "scope_reference_invalid",
        "One or more economics scope references are invalid",
        status_code=404,
    )


def _must_match(current: str | None, candidate: str | None) -> str | None:
    if not candidate:
        return current
    if current and str(current) != str(candidate):
        raise _invalid_reference()
    return str(candidate)


def _order_organization(order: Order) -> str | None:
    if (
        order.organization_id
        and order.company_id
        and order.organization_id != order.company_id
    ):
        return None
    return order.organization_id or order.company_id


@dataclass(frozen=True, slots=True)
class _ProviderScope:
    workspace_id: str | None
    order_id: str | None
    order_item_id: str | None
    catalog_item_id: str | None
    asset_id: str | None
    acquisition_id: str | None
    dataset_id: str | None
    processing_job_id: str | None
    fulfilment_job_id: str | None
    intelligence_acquisition_id: str | None
    notification_delivery_id: str | None
    report_id: str | None


def _validate_provider_scope(
    db: Session, payload: ProviderUsageCreate
) -> _ProviderScope:
    if db.get(Company, payload.organization_id) is None:
        raise _invalid_reference()

    workspace_id = payload.workspace_id
    order_id = payload.order_id
    order_item_id = payload.order_item_id
    catalog_item_id = payload.catalog_item_id
    asset_id = payload.asset_id
    acquisition_id = payload.acquisition_id
    dataset_id = payload.dataset_id
    processing_job_id = payload.processing_job_id
    fulfilment_job_id = payload.fulfilment_job_id

    def matches_org(candidate: str | None) -> None:
        if candidate and str(candidate) != str(payload.organization_id):
            raise _invalid_reference()

    if payload.processing_job_id:
        row = db.get(ProcessingJob, payload.processing_job_id)
        if row is None:
            raise _invalid_reference()
        matches_org(row.organization_id)
        workspace_id = _must_match(workspace_id, row.workspace_id)
        asset_id = _must_match(asset_id, row.asset_id)
        acquisition_id = _must_match(acquisition_id, row.acquisition_id)
        fulfilment_job_id = _must_match(fulfilment_job_id, row.fulfilment_job_id)

    if payload.intelligence_acquisition_id:
        row = db.get(IntelligenceAcquisition, payload.intelligence_acquisition_id)
        if row is None:
            raise _invalid_reference()
        matches_org(row.organization_id)
        workspace_id = _must_match(workspace_id, row.workspace_id)
        asset_id = _must_match(asset_id, row.asset_id)
        acquisition_id = _must_match(acquisition_id, row.acquisition_id)

    if payload.report_id:
        row = db.get(Report, payload.report_id)
        if row is None:
            raise _invalid_reference()
        matches_org(row.organization_id)
        workspace_id = _must_match(workspace_id, row.workspace_id)
        asset_id = _must_match(asset_id, row.asset_id)
        acquisition_id = _must_match(acquisition_id, row.acquisition_id)
        dataset_id = _must_match(dataset_id, row.output_dataset_id)

    if payload.notification_delivery_id:
        delivery = db.get(NotificationDelivery, payload.notification_delivery_id)
        notification = (
            db.get(Notification, delivery.notification_id)
            if delivery is not None
            else None
        )
        if delivery is None or notification is None:
            raise _invalid_reference()
        matches_org(notification.organization_id)
        workspace_id = _must_match(workspace_id, notification.workspace_id)

    if dataset_id:
        row = db.get(Dataset, dataset_id)
        if row is None:
            raise _invalid_reference()
        matches_org(row.company_id)
        workspace_id = _must_match(workspace_id, row.workspace_id)
        asset_id = _must_match(asset_id, row.asset_id)
        acquisition_id = _must_match(acquisition_id, row.mission_id)

    if acquisition_id:
        row = db.get(Acquisition, acquisition_id)
        if row is None:
            raise _invalid_reference()
        matches_org(row.organization_id)
        workspace_id = _must_match(workspace_id, row.workspace_id)
        asset_id = _must_match(asset_id, row.asset_id)
        order_id = _must_match(order_id, row.order_id)
        fulfilment_job_id = _must_match(fulfilment_job_id, row.fulfilment_job_id)

    if fulfilment_job_id:
        row = db.get(FulfilmentJob, fulfilment_job_id)
        if row is None:
            raise _invalid_reference()
        order_id = _must_match(order_id, row.order_id)
        order_item_id = _must_match(order_item_id, row.order_item_id)
        asset_id = _must_match(asset_id, row.asset_id)

    if order_item_id:
        row = db.get(OrderItem, order_item_id)
        if row is None:
            raise _invalid_reference()
        order_id = _must_match(order_id, row.order_id)
        catalog_item_id = _must_match(catalog_item_id, row.catalog_item_id)

    if order_id:
        row = db.get(Order, order_id)
        if row is None:
            raise _invalid_reference()
        matches_org(_order_organization(row))
        workspace_id = _must_match(workspace_id, row.workspace_id)

    if order_id and catalog_item_id and not order_item_id:
        belongs_to_order = (
            db.query(OrderItem.id)
            .filter(
                OrderItem.order_id == order_id,
                OrderItem.catalog_item_id == catalog_item_id,
            )
            .first()
        )
        if belongs_to_order is None:
            raise _invalid_reference()

    if asset_id:
        row = db.get(Asset, asset_id)
        if row is None or row.organization_id != payload.organization_id:
            raise _invalid_reference()
        workspace_id = _must_match(workspace_id, row.workspace_id)

    if catalog_item_id and db.get(CatalogItem, catalog_item_id) is None:
        raise _invalid_reference()
    if workspace_id:
        row = db.get(Account, workspace_id)
        if row is None or row.organization_id != payload.organization_id:
            raise _invalid_reference()

    return _ProviderScope(
        workspace_id=workspace_id,
        order_id=order_id,
        order_item_id=order_item_id,
        catalog_item_id=catalog_item_id,
        asset_id=asset_id,
        acquisition_id=acquisition_id,
        dataset_id=dataset_id,
        processing_job_id=payload.processing_job_id,
        fulfilment_job_id=fulfilment_job_id,
        intelligence_acquisition_id=payload.intelligence_acquisition_id,
        notification_delivery_id=payload.notification_delivery_id,
        report_id=payload.report_id,
    )


def record_provider_usage(
    db: Session,
    *,
    payload: ProviderUsageCreate,
    actor: User | None = None,
) -> tuple[ProviderUsage, bool]:
    try:
        sanitize_metadata(payload.metadata)
    except ValueError as exc:
        raise EconomicsError("unsafe_metadata", str(exc)) from exc
    request_hash = _request_hash(payload)
    existing = (
        db.query(ProviderUsage)
        .filter(
            ProviderUsage.organization_id == payload.organization_id,
            ProviderUsage.idempotency_key == payload.idempotency_key,
        )
        .one_or_none()
    )
    if existing is not None:
        if existing.request_sha256 != request_hash:
            raise EconomicsError(
                "idempotency_conflict",
                "The idempotency key was already used for different provider usage",
                status_code=409,
            )
        return existing, False

    scope = _validate_provider_scope(db, payload)

    total_cost = payload.total_cost
    if total_cost is None and payload.unit_cost is not None:
        try:
            with localcontext() as context:
                context.prec = 50
                total_cost = (payload.quantity * payload.unit_cost).quantize(
                    _MONEY, rounding=ROUND_HALF_UP
                )
        except InvalidOperation as exc:
            raise EconomicsError(
                "provider_cost_out_of_range",
                "Calculated provider cost is outside the supported range",
            ) from exc

    row = ProviderUsage(
        id=str(uuid.uuid4()),
        organization_id=payload.organization_id,
        workspace_id=scope.workspace_id,
        order_id=scope.order_id,
        order_item_id=scope.order_item_id,
        catalog_item_id=scope.catalog_item_id,
        asset_id=scope.asset_id,
        acquisition_id=scope.acquisition_id,
        dataset_id=scope.dataset_id,
        processing_job_id=scope.processing_job_id,
        fulfilment_job_id=scope.fulfilment_job_id,
        intelligence_acquisition_id=scope.intelligence_acquisition_id,
        notification_delivery_id=scope.notification_delivery_id,
        report_id=scope.report_id,
        provider=payload.provider,
        service=payload.service,
        usage_type=payload.usage_type,
        quantity=payload.quantity,
        unit=payload.unit,
        currency=payload.currency,
        unit_cost=payload.unit_cost,
        total_cost=total_cost,
        occurred_at=payload.occurred_at,
        provider_reference=payload.provider_reference,
        idempotency_key=payload.idempotency_key,
        request_sha256=request_hash,
        metadata_json=_json(payload.metadata),
        created_by_user_id=actor.id if actor is not None else None,
    )
    db.add(row)
    db.flush()
    record_audit_event(
        db,
        action="economics.provider_usage.recorded",
        resource_type="provider_usage",
        resource_id=row.id,
        actor=actor,
        organization_id=row.organization_id,
        workspace_id=row.workspace_id,
        details={
            "provider": row.provider,
            "service": row.service,
            "usage_type": row.usage_type,
            "cost_recorded": row.total_cost is not None,
        },
    )
    return row, True


@dataclass(frozen=True, slots=True)
class _CostScope:
    organization_id: str
    workspace_id: str | None
    order_item_id: str | None
    catalog_item_id: str | None
    asset_id: str | None
    fulfilment_job_id: str | None
    contractor_assignment_id: str | None


def _validate_cost_scope(db: Session, payload: InternalCostCreate) -> _CostScope:
    order = db.get(Order, payload.order_id)
    organization_id = _order_organization(order) if order is not None else None
    if order is None or not organization_id or db.get(Company, organization_id) is None:
        raise _invalid_reference()
    if order.workspace_id:
        workspace = db.get(Account, order.workspace_id)
        if workspace is None or workspace.organization_id != organization_id:
            raise _invalid_reference()
    if payload.currency != str(order.currency or "").upper():
        raise EconomicsError(
            "currency_mismatch",
            "Direct-cost currency must match the attributed order",
        )

    order_item_id = payload.order_item_id
    catalog_item_id = payload.catalog_item_id
    asset_id = payload.asset_id
    fulfilment_job_id = payload.fulfilment_job_id

    if order_item_id:
        item = db.get(OrderItem, order_item_id)
        if item is None or item.order_id != order.id:
            raise _invalid_reference()
        catalog_item_id = _must_match(catalog_item_id, item.catalog_item_id)
    if catalog_item_id and db.get(CatalogItem, catalog_item_id) is None:
        raise _invalid_reference()

    if fulfilment_job_id:
        job = db.get(FulfilmentJob, fulfilment_job_id)
        if job is None or job.order_id != order.id:
            raise _invalid_reference()
        order_item_id = _must_match(order_item_id, job.order_item_id)
        asset_id = _must_match(asset_id, job.asset_id)
        if order_item_id:
            item = db.get(OrderItem, order_item_id)
            if item is None or item.order_id != order.id:
                raise _invalid_reference()
            catalog_item_id = _must_match(catalog_item_id, item.catalog_item_id)

    if payload.contractor_assignment_id:
        assignment = db.get(ContractorAssignment, payload.contractor_assignment_id)
        if assignment is None:
            raise _invalid_reference()
        if assignment.order_id and assignment.order_id != order.id:
            raise _invalid_reference()
        if not assignment.order_id and not assignment.fulfilment_job_id:
            raise _invalid_reference()
        fulfilment_job_id = _must_match(fulfilment_job_id, assignment.fulfilment_job_id)
        if fulfilment_job_id:
            job = db.get(FulfilmentJob, fulfilment_job_id)
            if job is None or job.order_id != order.id:
                raise _invalid_reference()
            order_item_id = _must_match(order_item_id, job.order_item_id)
            asset_id = _must_match(asset_id, job.asset_id)
            if order_item_id:
                item = db.get(OrderItem, order_item_id)
                if item is None or item.order_id != order.id:
                    raise _invalid_reference()
                catalog_item_id = _must_match(catalog_item_id, item.catalog_item_id)

    if catalog_item_id and db.get(CatalogItem, catalog_item_id) is None:
        raise _invalid_reference()
    if catalog_item_id and not order_item_id:
        belongs_to_order = (
            db.query(OrderItem.id)
            .filter(
                OrderItem.order_id == order.id,
                OrderItem.catalog_item_id == catalog_item_id,
            )
            .first()
        )
        if belongs_to_order is None:
            raise _invalid_reference()

    if asset_id:
        asset = db.get(Asset, asset_id)
        if (
            asset is None
            or asset.organization_id != organization_id
            or (order.workspace_id and asset.workspace_id != order.workspace_id)
        ):
            raise _invalid_reference()

    return _CostScope(
        organization_id=organization_id,
        workspace_id=order.workspace_id,
        order_item_id=order_item_id,
        catalog_item_id=catalog_item_id,
        asset_id=asset_id,
        fulfilment_job_id=fulfilment_job_id,
        contractor_assignment_id=payload.contractor_assignment_id,
    )


def record_internal_cost(
    db: Session,
    *,
    payload: InternalCostCreate,
    actor: User,
) -> tuple[InternalCost, bool]:
    try:
        sanitize_metadata(payload.metadata)
    except ValueError as exc:
        raise EconomicsError("unsafe_metadata", str(exc)) from exc
    request_hash = _request_hash(payload)
    scope = _validate_cost_scope(db, payload)
    existing = (
        db.query(InternalCost)
        .filter(
            InternalCost.organization_id == scope.organization_id,
            InternalCost.idempotency_key == payload.idempotency_key,
        )
        .one_or_none()
    )
    if existing is not None:
        if existing.request_sha256 != request_hash:
            raise EconomicsError(
                "idempotency_conflict",
                "The idempotency key was already used for a different direct cost",
                status_code=409,
            )
        return existing, False

    row = InternalCost(
        id=str(uuid.uuid4()),
        organization_id=scope.organization_id,
        workspace_id=scope.workspace_id,
        order_id=payload.order_id,
        order_item_id=scope.order_item_id,
        catalog_item_id=scope.catalog_item_id,
        asset_id=scope.asset_id,
        fulfilment_job_id=scope.fulfilment_job_id,
        contractor_assignment_id=scope.contractor_assignment_id,
        cost_type=payload.cost_type.value,
        description=payload.description,
        amount=payload.amount.quantize(_MONEY, rounding=ROUND_HALF_UP),
        currency=payload.currency,
        incurred_at=payload.incurred_at,
        reference=payload.reference,
        idempotency_key=payload.idempotency_key,
        request_sha256=request_hash,
        metadata_json=_json(payload.metadata),
        created_by_user_id=actor.id,
    )
    db.add(row)
    db.flush()
    record_audit_event(
        db,
        action="economics.direct_cost.recorded",
        resource_type="internal_cost",
        resource_id=row.id,
        actor=actor,
        organization_id=row.organization_id,
        workspace_id=row.workspace_id,
        details={"cost_type": row.cost_type, "order_id": row.order_id},
    )
    return row, True


def provider_usage_out(row: ProviderUsage) -> ProviderUsageOut:
    return ProviderUsageOut(
        id=row.id,
        organization_id=row.organization_id,
        workspace_id=row.workspace_id,
        order_id=row.order_id,
        order_item_id=row.order_item_id,
        catalog_item_id=row.catalog_item_id,
        asset_id=row.asset_id,
        acquisition_id=row.acquisition_id,
        dataset_id=row.dataset_id,
        processing_job_id=row.processing_job_id,
        fulfilment_job_id=row.fulfilment_job_id,
        intelligence_acquisition_id=row.intelligence_acquisition_id,
        notification_delivery_id=row.notification_delivery_id,
        report_id=row.report_id,
        provider=row.provider,
        service=row.service,
        usage_type=row.usage_type,
        quantity=Decimal(row.quantity),
        unit=row.unit,
        currency=row.currency,
        unit_cost=Decimal(row.unit_cost) if row.unit_cost is not None else None,
        total_cost=Decimal(row.total_cost) if row.total_cost is not None else None,
        occurred_at=row.occurred_at,
        provider_reference=row.provider_reference,
        idempotency_key=row.idempotency_key,
        metadata=_decoded(row.metadata_json),
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
    )


def internal_cost_out(row: InternalCost) -> InternalCostOut:
    return InternalCostOut(
        id=row.id,
        organization_id=row.organization_id,
        workspace_id=row.workspace_id,
        order_id=row.order_id,
        order_item_id=row.order_item_id,
        catalog_item_id=row.catalog_item_id,
        asset_id=row.asset_id,
        fulfilment_job_id=row.fulfilment_job_id,
        contractor_assignment_id=row.contractor_assignment_id,
        cost_type=row.cost_type,
        description=row.description,
        amount=Decimal(row.amount),
        currency=row.currency,
        incurred_at=row.incurred_at,
        reference=row.reference,
        idempotency_key=row.idempotency_key,
        metadata=_decoded(row.metadata_json),
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
    )


def list_provider_usage(
    db: Session,
    *,
    organization_id: str,
    workspace_id: str | None = None,
    order_id: str | None = None,
    catalog_item_id: str | None = None,
    provider: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[ProviderUsage], int]:
    if db.get(Company, organization_id) is None:
        raise _invalid_reference()
    query = db.query(ProviderUsage).filter(
        ProviderUsage.organization_id == organization_id
    )
    if workspace_id:
        workspace = db.get(Account, workspace_id)
        if workspace is None or workspace.organization_id != organization_id:
            raise _invalid_reference()
        query = query.filter(ProviderUsage.workspace_id == workspace_id)
    if order_id:
        query = query.filter(ProviderUsage.order_id == order_id)
    if catalog_item_id:
        query = query.filter(ProviderUsage.catalog_item_id == catalog_item_id)
    if provider:
        query = query.filter(ProviderUsage.provider == provider.strip().lower())
    total = query.count()
    rows = (
        query.order_by(ProviderUsage.occurred_at.desc(), ProviderUsage.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return rows, total


def location_provider_usage_summary(
    db: Session,
    *,
    organization_id: str,
    since: datetime,
    workspace_id: str | None = None,
) -> ProviderUsageSummaryOut:
    if db.get(Company, organization_id) is None:
        raise _invalid_reference()
    query = db.query(
        ProviderUsage.provider,
        ProviderUsage.service,
        ProviderUsage.currency,
        func.count(ProviderUsage.id),
        func.sum(ProviderUsage.quantity),
        func.coalesce(func.sum(ProviderUsage.total_cost), 0),
    ).filter(
        ProviderUsage.organization_id == organization_id,
        ProviderUsage.occurred_at >= since,
        ProviderUsage.service.in_(
            {
                "places_autocomplete",
                "place_details",
                "routes_compute",
                "geocoding_reverse",
            }
        ),
    )
    if workspace_id:
        workspace = db.get(Account, workspace_id)
        if workspace is None or workspace.organization_id != organization_id:
            raise _invalid_reference()
        query = query.filter(ProviderUsage.workspace_id == workspace_id)
    rows = (
        query.group_by(
            ProviderUsage.provider,
            ProviderUsage.service,
            ProviderUsage.currency,
        )
        .order_by(ProviderUsage.provider, ProviderUsage.service)
        .all()
    )
    items = [
        ProviderUsageSummaryItemOut(
            provider=provider,
            service=service,
            currency=currency,
            call_count=int(call_count),
            quantity=Decimal(quantity),
            total_cost=Decimal(total_cost),
        )
        for provider, service, currency, call_count, quantity, total_cost in rows
    ]
    return ProviderUsageSummaryOut(
        items=items,
        total_calls=sum(item.call_count for item in items),
        generated_at=utc_now(),
    )


def list_internal_costs(
    db: Session,
    *,
    organization_id: str,
    workspace_id: str | None = None,
    order_id: str | None = None,
    catalog_item_id: str | None = None,
    cost_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[InternalCost], int]:
    if db.get(Company, organization_id) is None:
        raise _invalid_reference()
    query = db.query(InternalCost).filter(
        InternalCost.organization_id == organization_id
    )
    if workspace_id:
        workspace = db.get(Account, workspace_id)
        if workspace is None or workspace.organization_id != organization_id:
            raise _invalid_reference()
        query = query.filter(InternalCost.workspace_id == workspace_id)
    if order_id:
        query = query.filter(InternalCost.order_id == order_id)
    if catalog_item_id:
        query = query.filter(InternalCost.catalog_item_id == catalog_item_id)
    if cost_type:
        query = query.filter(InternalCost.cost_type == cost_type.strip().upper())
    total = query.count()
    rows = (
        query.order_by(InternalCost.incurred_at.desc(), InternalCost.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return rows, total


def _revenue_order(order: Order) -> bool:
    return (
        str(order.fulfilment_status or "").upper() not in _NON_REVENUE_STATES
        and str(order.payment_status or "").upper() not in _NON_REVENUE_PAYMENTS
    )


def _unit_economics(
    *,
    scope_type: EconomicsScopeType,
    scope_id: str,
    scope_name: str,
    orders: Iterable[Order],
    line_items: Iterable[OrderItem],
    costs: Iterable[InternalCost],
    usage: Iterable[ProviderUsage],
) -> UnitEconomicsOut:
    orders = list(orders)
    line_items = list(line_items)
    eligible_order_ids = {row.id for row in orders if _revenue_order(row)}
    revenue: defaultdict[str, Decimal] = defaultdict(Decimal)
    internal: defaultdict[str, Decimal] = defaultdict(Decimal)
    provider: defaultdict[str, Decimal] = defaultdict(Decimal)
    breakdown: defaultdict[tuple[str, str], Decimal] = defaultdict(Decimal)
    order_ids: defaultdict[str, set[str]] = defaultdict(set)
    line_counts: defaultdict[str, int] = defaultdict(int)

    if scope_type is EconomicsScopeType.CATALOG_ITEM:
        for item in line_items:
            if item.order_id not in eligible_order_ids:
                continue
            currency = str(item.currency or "").upper()
            revenue[currency] += Decimal(item.line_total or 0)
            order_ids[currency].add(item.order_id)
            line_counts[currency] += 1
    else:
        for order in orders:
            if order.id not in eligible_order_ids:
                continue
            currency = str(order.currency or "").upper()
            revenue[currency] += Decimal(order.total or 0)
            order_ids[currency].add(order.id)
            line_counts[currency] += sum(
                1 for item in line_items if item.order_id == order.id
            )

    for row in costs:
        currency = row.currency.upper()
        value = Decimal(row.amount or 0)
        internal[currency] += value
        breakdown[(currency, row.cost_type)] += value
        order_ids[currency].add(row.order_id)
    for row in usage:
        if row.total_cost is None or not row.currency:
            continue
        currency = row.currency.upper()
        value = Decimal(row.total_cost)
        provider[currency] += value
        breakdown[(currency, "PROVIDER")] += value
        if row.order_id:
            order_ids[currency].add(row.order_id)

    currencies = sorted(set(revenue) | set(internal) | set(provider))
    summaries: list[EconomicsCurrencySummaryOut] = []
    for currency in currencies:
        revenue_value = revenue[currency].quantize(_MONEY)
        internal_value = internal[currency].quantize(_MONEY)
        provider_value = provider[currency].quantize(_MONEY)
        direct = (internal_value + provider_value).quantize(_MONEY)
        contribution = (revenue_value - direct).quantize(_MONEY)
        margin = (
            ((contribution / revenue_value) * Decimal("100")).quantize(_PERCENT)
            if revenue_value > 0
            else None
        )
        summaries.append(
            EconomicsCurrencySummaryOut(
                currency=currency,
                revenue=revenue_value,
                internal_cost=internal_value,
                provider_cost=provider_value,
                direct_cost=direct,
                gross_contribution=contribution,
                gross_margin_percent=margin,
                order_count=len(order_ids[currency]),
                line_item_count=line_counts[currency],
                cost_breakdown=[
                    CostBreakdownOut(cost_type=cost_type, amount=value.quantize(_MONEY))
                    for (breakdown_currency, cost_type), value in sorted(
                        breakdown.items()
                    )
                    if breakdown_currency == currency
                ],
            )
        )
    return UnitEconomicsOut(
        scope_type=scope_type,
        scope_id=scope_id,
        scope_name=scope_name,
        currencies=summaries,
        generated_at=utc_now(),
    )


def order_economics(db: Session, order_id: str) -> UnitEconomicsOut:
    order = db.get(Order, order_id)
    if order is None or not _order_organization(order):
        raise _invalid_reference()
    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    costs = db.query(InternalCost).filter(InternalCost.order_id == order.id).all()
    usage = db.query(ProviderUsage).filter(ProviderUsage.order_id == order.id).all()
    return _unit_economics(
        scope_type=EconomicsScopeType.ORDER,
        scope_id=order.id,
        scope_name=order.order_number or order.id,
        orders=[order],
        line_items=items,
        costs=costs,
        usage=usage,
    )


def catalog_item_economics(db: Session, catalog_item_id: str) -> UnitEconomicsOut:
    catalog_item = db.get(CatalogItem, catalog_item_id)
    if catalog_item is None:
        raise _invalid_reference()
    items = (
        db.query(OrderItem).filter(OrderItem.catalog_item_id == catalog_item_id).all()
    )
    order_ids = {row.order_id for row in items}
    orders = db.query(Order).filter(Order.id.in_(order_ids)).all() if order_ids else []
    costs = (
        db.query(InternalCost)
        .filter(InternalCost.catalog_item_id == catalog_item_id)
        .all()
    )
    usage = (
        db.query(ProviderUsage)
        .filter(ProviderUsage.catalog_item_id == catalog_item_id)
        .all()
    )
    return _unit_economics(
        scope_type=EconomicsScopeType.CATALOG_ITEM,
        scope_id=catalog_item.id,
        scope_name=catalog_item.name,
        orders=orders,
        line_items=items,
        costs=costs,
        usage=usage,
    )


def organization_economics(db: Session, organization_id: str) -> UnitEconomicsOut:
    organization = db.get(Company, organization_id)
    if organization is None:
        raise _invalid_reference()
    orders = (
        db.query(Order)
        .filter(
            or_(
                Order.organization_id == organization_id,
                Order.company_id == organization_id,
            )
        )
        .all()
    )
    orders = [row for row in orders if _order_organization(row) == organization_id]
    order_ids = {row.id for row in orders}
    items = (
        db.query(OrderItem).filter(OrderItem.order_id.in_(order_ids)).all()
        if order_ids
        else []
    )
    costs = (
        db.query(InternalCost)
        .filter(InternalCost.organization_id == organization_id)
        .all()
    )
    usage = (
        db.query(ProviderUsage)
        .filter(ProviderUsage.organization_id == organization_id)
        .all()
    )
    return _unit_economics(
        scope_type=EconomicsScopeType.ORGANIZATION,
        scope_id=organization.id,
        scope_name=organization.name,
        orders=orders,
        line_items=items,
        costs=costs,
        usage=usage,
    )


__all__ = [
    "catalog_item_economics",
    "internal_cost_out",
    "list_internal_costs",
    "list_provider_usage",
    "order_economics",
    "organization_economics",
    "provider_usage_out",
    "record_internal_cost",
    "record_provider_usage",
]
