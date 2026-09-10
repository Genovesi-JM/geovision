"""Commercial order application services shared by API and provider callbacks."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, false, or_
from sqlalchemy.orm import Session

from app.core.event_names import EventNames
from app.core.time import utc_now
from app.models import (
    Account,
    AccountMember,
    AuditLog,
    CatalogItem,
    Company,
    Deliverable,
    Order,
    OrderEvent,
    OrderItem,
    Payment,
    User,
)
from app.modules.orders.domain import (
    FulfilmentStatus,
    OrderLifecycleError,
    OrderPaymentStatus,
    classify_order,
    fulfilment_from_legacy,
    legacy_status,
    payment_from_provider,
    require_transition,
)
from app.modules.orders.schemas import DraftOrderCreate
from app.services.event_outbox import enqueue_domain_event


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _dict(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _money(value: Any) -> int:
    return int(Decimal(str(value or 0)))


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _audit(
    db: Session,
    *,
    actor: User | None,
    action: str,
    order: Order,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=actor.id if actor else None,
            user_email=actor.email if actor else None,
            action=action,
            resource_type="order",
            resource_id=order.id,
            details=_dumps(
                {
                    "organization_id": order.organization_id or order.company_id,
                    **(details or {}),
                }
            ),
        )
    )


def _event(
    db: Session,
    *,
    order: Order,
    event_type: str,
    title: str,
    description: str | None,
    actor_name: str,
    customer_visible: bool,
    metadata: dict[str, Any] | None = None,
) -> OrderEvent:
    row = OrderEvent(
        order_id=order.id,
        event_type=event_type,
        title=title,
        description=description,
        actor_name=actor_name,
        is_customer_visible=customer_visible,
        metadata_json=_dumps(metadata or {}),
    )
    db.add(row)
    return row


def _domain_event(
    db: Session,
    *,
    order: Order,
    name: str,
    key: str,
    payload: dict[str, Any] | None = None,
    causation_id: str | None = None,
) -> None:
    enqueue_domain_event(
        db,
        name=name,
        aggregate_type="order",
        aggregate_id=order.id,
        idempotency_key=key,
        correlation_id=order.id,
        causation_id=causation_id,
        payload={
            "order_id": order.id,
            "organization_id": order.organization_id or order.company_id,
            "workspace_id": order.workspace_id,
            **(payload or {}),
        },
    )


def enqueue_order_created_erp(db: Session, *, order: Order) -> None:
    """Stage the ERP order command in the order's own transaction.

    Callers must invoke this before their single business commit. The payload
    is built only from the server-owned order snapshot and the creation key is
    stable, so canonical and compatibility routes cannot enqueue duplicates.
    """

    from app.services.erp_sync import enqueue_erp_event

    # Creation paths add line items before this helper. Flush once so defaults,
    # timestamps, and the relationship snapshot are available without commit.
    db.flush()
    created_at = order.created_at or utc_now()
    organization_id = order.organization_id or order.company_id
    organization = db.get(Company, organization_id) if organization_id else None
    customer = db.get(User, order.user_id) if order.user_id else None
    customer_reference = organization_id or order.user_id
    contact_snapshot = {
        "geovision_id": customer_reference,
        "name": (
            organization.name
            if organization is not None
            else getattr(getattr(customer, "profile", None), "full_name", None)
        ),
        "email": (
            organization.email
            if organization is not None
            else getattr(customer, "email", None)
        ),
        "phone": (
            organization.phone
            if organization is not None
            else getattr(getattr(customer, "profile", None), "phone", None)
        ),
        "tax_id": organization.tax_id if organization is not None else None,
        "address": organization.address if organization is not None else None,
        "country": organization.country if organization is not None else None,
    }
    enqueue_erp_event(
        db,
        company_id=organization_id,
        aggregate_type="order",
        aggregate_id=order.id,
        event_type=EventNames.ORDER_CREATED,
        version="created.v1",
        payload={
            "customer_reference": customer_reference,
            "customer": contact_snapshot,
            "transaction_date": created_at.date().isoformat(),
            "currency": order.currency,
            "order_type": order.order_type,
            "order_number": order.order_number,
            "total_cents": _money(order.total),
            "items": [
                {
                    "item_code": (
                        item.sku
                        or item.catalog_item_id
                        or item.product_id
                        or item.id
                    ),
                    "item_name": item.name,
                    "qty": item.qty,
                    "rate": _money(item.unit_price) / 100,
                }
                for item in order.items
            ],
        },
    )


def _canonical_status(order: Order) -> FulfilmentStatus:
    try:
        return FulfilmentStatus(order.fulfilment_status)
    except (AttributeError, ValueError):
        return fulfilment_from_legacy(order.status)


def _catalog_price(item: CatalogItem, currency: str) -> int | None:
    pricing = _dict(item.pricing_json)
    amount = pricing.get(currency)
    if isinstance(amount, int) and not isinstance(amount, bool) and amount >= 0:
        return amount
    if item.currency == currency and item.unit_amount is not None:
        return int(item.unit_amount)
    return None


def create_draft_order(
    db: Session,
    *,
    actor: User,
    data: DraftOrderCreate,
) -> Order:
    organization = db.get(Company, data.organization_id)
    if organization is None or organization.status == "suspended":
        raise OrderLifecycleError("organization_not_found", "Organization is not available")

    if data.workspace_id:
        workspace = db.get(Account, data.workspace_id)
        if workspace is None or workspace.organization_id != organization.id:
            raise OrderLifecycleError("workspace_not_found", "Workspace is not available")

    if data.customer_id and db.get(User, data.customer_id) is None:
        raise OrderLifecycleError("customer_not_found", "Customer is not available")

    resolved: list[tuple[CatalogItem, Any, int, int, int, float, int]] = []
    item_types: list[str] = []
    subtotal = 0
    discount_total = 0
    tax_total = 0
    for requested in data.items:
        item = db.get(CatalogItem, requested.catalog_item_id)
        if item is None or item.status == "ARCHIVED":
            raise OrderLifecycleError("catalog_item_not_found", "Catalogue item is not available")
        unit_amount = requested.unit_amount
        if unit_amount is None:
            unit_amount = _catalog_price(item, data.currency)
        if unit_amount is None:
            raise OrderLifecycleError(
                "price_required",
                f"A {data.currency} price is required for catalogue item {item.code}",
            )
        gross = unit_amount * requested.quantity
        if requested.discount_amount > gross:
            raise OrderLifecycleError(
                "invalid_discount", "Line discount cannot exceed its gross amount"
            )
        line_total = gross - requested.discount_amount
        metadata = _dict(item.metadata_json)
        try:
            tax_rate = max(0.0, float(metadata.get("tax_rate", 0)))
        except (TypeError, ValueError):
            tax_rate = 0.0
        tax_amount = int(line_total - line_total / (1 + tax_rate)) if tax_rate else 0
        resolved.append(
            (
                item,
                requested,
                unit_amount,
                line_total,
                requested.discount_amount,
                tax_rate,
                tax_amount,
            )
        )
        item_types.append(item.item_type)
        subtotal += gross
        discount_total += requested.discount_amount
        tax_total += tax_amount

    now = utc_now()
    order = Order(
        id=str(uuid.uuid4()),
        order_number=None,
        user_id=data.customer_id,
        company_id=organization.id,
        organization_id=organization.id,
        workspace_id=data.workspace_id,
        order_type=classify_order(item_types).value,
        status="created",
        fulfilment_status=FulfilmentStatus.DRAFT.value,
        payment_status=(
            OrderPaymentStatus.NOT_REQUIRED.value
            if subtotal - discount_total == 0
            else OrderPaymentStatus.PENDING.value
        ),
        currency=data.currency,
        subtotal=subtotal,
        discount_total=discount_total,
        tax_amount=tax_total,
        shipping_fee=0,
        total=subtotal - discount_total,
        customer_notes=data.customer_notes,
        internal_notes=data.internal_notes,
        metadata_json=_dumps({"created_via": "internal_order_api"}),
        created_at=now,
        updated_at=now,
    )
    db.add(order)
    db.flush()
    order.order_number = f"GV-{now.year}-{order.id.split('-')[0].upper()}"

    for item, requested, unit_amount, line_total, discount, tax_rate, tax_amount in resolved:
        db.add(
            OrderItem(
                order_id=order.id,
                catalog_item_id=item.id,
                sku=item.code,
                name=item.name,
                product_type=item.item_type.lower(),
                catalog_item_type=item.item_type,
                currency=data.currency,
                unit_price=unit_amount,
                qty=requested.quantity,
                line_total=line_total,
                tax_rate=tax_rate,
                tax_amount=tax_amount,
                discount_amount=discount,
                status="pending",
                pricing_snapshot_json=_dumps(
                    {
                        "catalog_item_id": item.id,
                        "code": item.code,
                        "name": item.name,
                        "item_type": item.item_type,
                        "price_model": item.price_model,
                        "currency": data.currency,
                        "unit_amount": unit_amount,
                        "quantity": requested.quantity,
                        "discount_amount": discount,
                        "tax_rate": tax_rate,
                        "captured_at": now.isoformat(),
                    }
                ),
                fulfilment_hints_json=_dumps(
                    {
                        "fulfilment_type": item.fulfilment_type,
                        "requires_site": item.requires_site,
                        "requires_scheduling": item.requires_scheduling,
                        "duration_hours": item.duration_hours,
                    }
                ),
            )
        )

    _event(
        db,
        order=order,
        event_type="order_created",
        title="Order draft created",
        description="A GeoVision commercial order draft was created.",
        actor_name=actor.email,
        customer_visible=bool(data.customer_id),
    )
    _audit(db, actor=actor, action="order.draft.created", order=order)
    _domain_event(
        db,
        order=order,
        name=EventNames.ORDER_CREATED,
        key=f"order:{order.id}:created",
        payload={
            "order_number": order.order_number,
            "order_type": order.order_type,
            "currency": order.currency,
            "total": int(order.total or 0),
        },
    )
    enqueue_order_created_erp(db, order=order)
    return order


_PAYMENT_GATED_TARGETS = frozenset(
    {
        FulfilmentStatus.PAYMENT_AUTHORIZED,
        FulfilmentStatus.PAID,
        FulfilmentStatus.SCHEDULING,
        FulfilmentStatus.ASSIGNED,
        FulfilmentStatus.IN_PROGRESS,
        FulfilmentStatus.DATA_UPLOADED,
        FulfilmentStatus.PROCESSING,
        FulfilmentStatus.QA_REVIEW,
        FulfilmentStatus.RESULTS_READY,
        FulfilmentStatus.DELIVERED,
        FulfilmentStatus.COMPLETED,
    }
)


def transition_order(
    db: Session,
    *,
    order: Order,
    target: FulfilmentStatus,
    actor: User | None,
    actor_name: str | None = None,
    reason: str | None = None,
    customer_visible: bool = True,
    expected_version: int | None = None,
) -> bool:
    current = _canonical_status(order)
    if expected_version is not None and order.lifecycle_version != expected_version:
        raise OrderLifecycleError(
            "version_conflict", "Order changed since it was last read"
        )
    if target == current:
        return False
    require_transition(current, target)

    if target in {
        FulfilmentStatus.CANCELLED,
        FulfilmentStatus.FAILED,
        FulfilmentStatus.NEEDS_REFLIGHT,
        FulfilmentStatus.ON_HOLD,
    } and not (reason or "").strip():
        raise OrderLifecycleError("reason_required", f"{target.value} requires a reason")

    try:
        payment_status = OrderPaymentStatus(order.payment_status)
    except (AttributeError, ValueError):
        payment_status = OrderPaymentStatus.PENDING
    if target in _PAYMENT_GATED_TARGETS:
        allowed_payment_states = {
            OrderPaymentStatus.AUTHORIZED,
            OrderPaymentStatus.PAID,
            OrderPaymentStatus.NOT_REQUIRED,
        }
        if payment_status not in allowed_payment_states:
            raise OrderLifecycleError(
                "payment_required",
                "Settlement must be authorized or paid before fulfilment can advance",
            )
        if target == FulfilmentStatus.PAID and payment_status not in {
            OrderPaymentStatus.PAID,
            OrderPaymentStatus.NOT_REQUIRED,
        }:
            raise OrderLifecycleError(
                "payment_not_settled", "The payment provider has not reported settlement"
            )

    now = utc_now()
    order.previous_fulfilment_status = current.value
    order.fulfilment_status = target.value
    order.status = legacy_status(target)
    order.lifecycle_version = int(order.lifecycle_version or 0) + 1
    order.updated_at = now
    if target == FulfilmentStatus.CONFIRMED:
        order.confirmed_at = now
    elif target == FulfilmentStatus.IN_PROGRESS and order.actual_start is None:
        order.actual_start = now
    elif target == FulfilmentStatus.DELIVERED:
        order.actual_delivery = now
    elif target == FulfilmentStatus.COMPLETED:
        order.actual_end = now
        order.completed_at = now
    elif target == FulfilmentStatus.CANCELLED:
        order.cancelled_at = now
    elif target == FulfilmentStatus.FAILED:
        order.failed_at = now
    if target == FulfilmentStatus.ON_HOLD:
        order.on_hold_reason = reason.strip() if reason else None
    elif current == FulfilmentStatus.ON_HOLD:
        order.on_hold_reason = None

    _event(
        db,
        order=order,
        event_type=f"fulfilment_{target.value.lower()}",
        title=f"Order {target.value.replace('_', ' ').lower()}",
        description=reason,
        actor_name=actor.email if actor else (actor_name or "GeoVision"),
        customer_visible=customer_visible,
        metadata={"from": current.value, "to": target.value},
    )
    _audit(
        db,
        actor=actor,
        action="order.fulfilment.transitioned",
        order=order,
        details={"from": current.value, "to": target.value},
    )
    _domain_event(
        db,
        order=order,
        name=EventNames.ORDER_STATE_CHANGED,
        key=f"order:{order.id}:state:{order.lifecycle_version}",
        payload={
            "from": current.value,
            "to": target.value,
            "reason": reason,
            "customer_visible": customer_visible,
        },
    )
    return True


def apply_payment_state(
    db: Session,
    *,
    payment: Payment,
    provider_status: str,
    source_event_id: str | None = None,
    actor_name: str = "Payment provider",
) -> bool:
    """Project provider settlement onto an order without conflating fulfilment."""

    order = db.get(Order, payment.order_id)
    if order is None:
        return False
    target_payment = payment_from_provider(provider_status)
    try:
        current_payment = OrderPaymentStatus(order.payment_status)
    except (AttributeError, ValueError):
        current_payment = OrderPaymentStatus.PENDING
    if target_payment == current_payment:
        return False

    now = utc_now()
    order.payment_status = target_payment.value
    order.lifecycle_version = int(order.lifecycle_version or 0) + 1
    order.updated_at = now
    current_fulfilment = _canonical_status(order)
    target_fulfilment: FulfilmentStatus | None = None
    if target_payment == OrderPaymentStatus.AUTHORIZED:
        payment.authorized_at = payment.authorized_at or now
        if current_fulfilment == FulfilmentStatus.CONFIRMED:
            target_fulfilment = FulfilmentStatus.PAYMENT_AUTHORIZED
    elif target_payment == OrderPaymentStatus.PAID:
        payment.completed_at = payment.completed_at or now
        order.payment_confirmed_at = order.payment_confirmed_at or now
        if current_fulfilment in {
            FulfilmentStatus.CONFIRMED,
            FulfilmentStatus.PAYMENT_AUTHORIZED,
        }:
            target_fulfilment = FulfilmentStatus.PAID
    elif target_payment == OrderPaymentStatus.FAILED:
        payment.failed_at = payment.failed_at or now

    if target_fulfilment is not None:
        order.previous_fulfilment_status = current_fulfilment.value
        order.fulfilment_status = target_fulfilment.value
        order.status = legacy_status(target_fulfilment)
    elif target_payment == OrderPaymentStatus.REFUNDED:
        order.status = "refunded"
    elif target_payment == OrderPaymentStatus.PARTIALLY_REFUNDED:
        order.status = "partially_refunded"

    _event(
        db,
        order=order,
        event_type=f"payment_{target_payment.value.lower()}",
        title=f"Payment {target_payment.value.replace('_', ' ').lower()}",
        description=None,
        actor_name=actor_name,
        customer_visible=True,
        metadata={
            "payment_id": payment.id,
            "provider": payment.provider,
            "source_event_id": source_event_id,
        },
    )
    payment_event_name = {
        OrderPaymentStatus.AUTHORIZED: EventNames.PAYMENT_AUTHORIZED,
        OrderPaymentStatus.PAID: EventNames.PAYMENT_SETTLED,
        OrderPaymentStatus.FAILED: EventNames.PAYMENT_FAILED,
    }.get(target_payment, EventNames.PAYMENT_STATE_CHANGED)
    _domain_event(
        db,
        order=order,
        name=payment_event_name,
        key=(
            f"payment:{payment.id}:{target_payment.value}:"
            f"{source_event_id or order.lifecycle_version}"
        ),
        causation_id=source_event_id,
        payload={
            "payment_id": payment.id,
            "provider": payment.provider,
            "from": current_payment.value,
            "to": target_payment.value,
            "source_event_id": source_event_id,
        },
    )
    return True


def _customer_order_scope_filter(db: Session, user: User):
    """Build the selected-workspace boundary for canonical customer orders.

    Old orders may not have a workspace.  They remain visible only where the
    missing scope has one possible interpretation; once an organization has
    multiple active workspaces, organization-only rows fail closed.
    """

    context = getattr(user, "_authorization_context", None)
    permissions = frozenset(getattr(context, "permissions", frozenset()))
    active_organization_id = getattr(context, "active_organization_id", None)
    active_workspace_id = getattr(context, "active_workspace_id", None)
    owner_filter = Order.user_id == user.id

    # Users with no canonical customer context keep access to their own
    # genuinely legacy, unscoped orders.  A workspace-bound row is never
    # exposed without an authenticated selected workspace.
    if not active_organization_id and not active_workspace_id:
        return and_(owner_filter, Order.workspace_id.is_(None))
    if not active_organization_id:
        return false()
    if not active_workspace_id:
        return and_(
            owner_filter,
            Order.workspace_id.is_(None),
            or_(
                Order.organization_id.is_(None),
                Order.organization_id == active_organization_id,
            ),
            or_(
                Order.company_id.is_(None),
                Order.company_id == active_organization_id,
            ),
        )

    organization_consistent = and_(
        or_(
            Order.organization_id.is_(None),
            Order.organization_id == active_organization_id,
        ),
        or_(
            Order.company_id.is_(None),
            Order.company_id == active_organization_id,
        ),
    )
    eligibility = owner_filter
    if "billing:read" in permissions:
        eligibility = or_(
            eligibility,
            Order.organization_id == active_organization_id,
            Order.company_id == active_organization_id,
        )

    active_organization_workspaces = (
        db.query(Account.id)
        .filter(
            Account.organization_id == active_organization_id,
            Account.status == "active",
        )
        .limit(2)
        .all()
    )
    sole_organization_workspace = active_organization_workspaces == [
        (active_workspace_id,)
    ]
    accessible_workspaces = (
        db.query(AccountMember.account_id)
        .join(Account, Account.id == AccountMember.account_id)
        .filter(
            AccountMember.user_id == user.id,
            AccountMember.status == "active",
            Account.status == "active",
        )
        .limit(2)
        .all()
    )
    sole_accessible_workspace = accessible_workspaces == [(active_workspace_id,)]

    scoped_workspace_filters = [Order.workspace_id == active_workspace_id]
    if sole_organization_workspace:
        scoped_workspace_filters.append(
            and_(
                Order.workspace_id.is_(None),
                or_(
                    Order.organization_id == active_organization_id,
                    Order.company_id == active_organization_id,
                ),
            )
        )
    scope_filters = [
        and_(organization_consistent, or_(*scoped_workspace_filters))
    ]
    if sole_accessible_workspace:
        # Some pre-workspace orders carry an organization snapshot which no
        # longer has a membership relation.  Ownership plus exactly one
        # accessible workspace is the only non-ambiguous compatibility map.
        scope_filters.append(
            and_(owner_filter, Order.workspace_id.is_(None))
        )
    return and_(eligibility, or_(*scope_filters))


def customer_can_view(order: Order, user: User, *, db: Session) -> bool:
    return (
        db.query(Order.id)
        .filter(
            Order.id == order.id,
            _customer_order_scope_filter(db, user),
        )
        .first()
        is not None
    )


def customer_orders(db: Session, user: User, *, limit: int = 100) -> list[Order]:
    return (
        db.query(Order)
        .filter(_customer_order_scope_filter(db, user))
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(limit)
        .all()
    )


def _item_out(item: OrderItem) -> dict[str, Any]:
    snapshot = _dict(item.pricing_snapshot_json)
    return {
        "id": item.id,
        "catalog_item_id": item.catalog_item_id,
        "catalog_item_type": item.catalog_item_type or item.product_type,
        "code": item.sku,
        "name": item.name,
        "quantity": item.qty,
        "unit_amount": _money(item.unit_price),
        "discount_amount": _money(item.discount_amount),
        "line_total": _money(item.line_total),
        "tax_rate": float(item.tax_rate or 0),
        "tax_amount": _money(item.tax_amount),
        "currency": item.currency,
        "status": item.status,
        "scheduled_date": _iso(item.scheduled_date),
        "pricing_snapshot": snapshot,
        "fulfilment_hints": _dict(item.fulfilment_hints_json),
    }


def _event_out(event: OrderEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "title": event.title,
        "description": event.description,
        "actor_name": event.actor_name,
        "created_at": event.created_at.isoformat(),
    }


def _deliverable_out(deliverable: Deliverable) -> dict[str, Any]:
    return {
        "id": deliverable.id,
        "order_item_id": deliverable.order_item_id,
        "name": deliverable.name,
        "description": deliverable.description,
        "deliverable_type": deliverable.deliverable_type,
        "file_size": deliverable.file_size,
        "mime_type": deliverable.mime_type,
        "download_url": deliverable.download_url,
        "is_ready": deliverable.is_ready,
        "created_at": deliverable.created_at.isoformat(),
    }


def order_summary(order: Order) -> dict[str, Any]:
    return {
        "id": order.id,
        "order_number": order.order_number,
        "order_type": order.order_type,
        "fulfilment_status": _canonical_status(order).value,
        "payment_status": order.payment_status,
        "currency": order.currency,
        "subtotal": _money(order.subtotal),
        "discount_total": _money(order.discount_total),
        "tax_amount": _money(order.tax_amount),
        "shipping_fee": _money(order.shipping_fee),
        "total": _money(order.total),
        "item_count": len(order.items),
        "lifecycle_version": order.lifecycle_version,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
    }


def order_detail(order: Order, *, internal: bool = False) -> dict[str, Any]:
    events = sorted(order.events_rel or [], key=lambda event: (event.created_at, event.id))
    if not internal:
        events = [event for event in events if event.is_customer_visible]
    payload = {
        **order_summary(order),
        "organization_id": order.organization_id or order.company_id,
        "workspace_id": order.workspace_id,
        "customer_id": order.user_id,
        "site_id": order.site_id,
        "payment_method": order.payment_method,
        "customer_notes": order.customer_notes,
        "delivery_method": order.delivery_method,
        "assigned_team": order.assigned_team,
        "scheduled_start": _iso(order.scheduled_start),
        "scheduled_end": _iso(order.scheduled_end),
        "actual_start": _iso(order.actual_start),
        "actual_end": _iso(order.actual_end),
        "estimated_delivery": _iso(order.estimated_delivery),
        "actual_delivery": _iso(order.actual_delivery),
        "completed_at": _iso(order.completed_at),
        "cancelled_at": _iso(order.cancelled_at),
        "items": [_item_out(item) for item in order.items],
        "events": [_event_out(event) for event in events],
        "deliverables": [
            _deliverable_out(row) for row in (order.deliverables_rel or [])
        ],
    }
    if internal:
        payload.update(
            {
                "legacy_status": order.status,
                "payment_id": order.payment_intent_id,
                "payment_reference": order.payment_reference,
                "internal_notes": order.internal_notes,
                "on_hold_reason": order.on_hold_reason,
                "failed_at": _iso(order.failed_at),
            }
        )
    return payload


__all__ = [
    "apply_payment_state",
    "create_draft_order",
    "customer_can_view",
    "customer_orders",
    "enqueue_order_created_erp",
    "order_detail",
    "order_summary",
    "transition_order",
]
