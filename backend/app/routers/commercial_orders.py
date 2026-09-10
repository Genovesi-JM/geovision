"""Canonical customer and internal commercial-order API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import Order, User
from app.modules.orders.domain import FulfilmentStatus, OrderLifecycleError
from app.modules.orders.schemas import (
    CheckoutOut,
    CheckoutRequest,
    DraftOrderCreate,
    FulfilmentTransitionRequest,
    InternalOrderOut,
    OrderDetailOut,
    OrderSummaryOut,
)
from app.modules.orders.services import (
    create_draft_order,
    customer_can_view,
    customer_orders,
    order_detail,
    order_summary,
    transition_order,
)
from app.modules.operations.job_schemas import CustomerOrderProgressOut
from app.modules.operations.job_services import customer_order_progress
from app.modules.organizations.domain import internal_permissions
from app.modules.organizations.services import active_internal_roles
from app.services.orders import PaymentMethod, get_order_service


router = APIRouter(prefix="/orders", tags=["orders"])

_ORDER_STAFF_PERMISSIONS = {
    "platform:admin",
    "operations:access",
    "sales:internal",
    "billing:internal",
    "inventory:internal",
}


def require_order_staff(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    permissions = internal_permissions(active_internal_roles(db, user))
    if not permissions.intersection(_ORDER_STAFF_PERMISSIONS):
        raise HTTPException(status_code=403, detail="GeoVision order staff permission required")
    return user


OrderStaff = Annotated[User, Depends(require_order_staff)]


def _raise_order_error(exc: OrderLifecycleError) -> None:
    code_status = {
        "organization_not_found": status.HTTP_404_NOT_FOUND,
        "workspace_not_found": status.HTTP_404_NOT_FOUND,
        "customer_not_found": status.HTTP_404_NOT_FOUND,
        "catalog_item_not_found": status.HTTP_404_NOT_FOUND,
        "version_conflict": status.HTTP_409_CONFLICT,
        "invalid_transition": status.HTTP_409_CONFLICT,
    }
    raise HTTPException(
        status_code=code_status.get(exc.code, status.HTTP_422_UNPROCESSABLE_ENTITY),
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


@router.post("/checkout/{cart_id}", response_model=CheckoutOut)
async def checkout(
    cart_id: str,
    request: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(
        default=None, alias="Idempotency-Key", min_length=8, max_length=160
    ),
):
    try:
        payment_method = PaymentMethod(request.payment_method)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unsupported payment method") from exc
    if request.currency not in {"AOA", "USD", "EUR"}:
        raise HTTPException(status_code=422, detail="Unsupported currency")

    context = getattr(user, "_authorization_context", None)
    result = await get_order_service(db).checkout(
        cart_id=cart_id,
        user_id=user.id,
        payment_method=payment_method,
        billing_info=request.billing_info,
        customer_notes=request.customer_notes,
        currency=request.currency,
        organization_id=getattr(context, "active_organization_id", None),
        workspace_id=getattr(context, "active_workspace_id", None),
        idempotency_key=idempotency_key,
    )
    if not result.success:
        raise HTTPException(status_code=409, detail=result.error or "Checkout failed")
    return CheckoutOut(**result.__dict__)


@router.post(
    "/internal",
    response_model=InternalOrderOut,
    status_code=status.HTTP_201_CREATED,
)
def create_internal_order(
    data: DraftOrderCreate,
    actor: OrderStaff,
    db: Session = Depends(get_db),
):
    try:
        order = create_draft_order(db, actor=actor, data=data)
        db.commit()
        db.refresh(order)
        return order_detail(order, internal=True)
    except OrderLifecycleError as exc:
        db.rollback()
        _raise_order_error(exc)


@router.get("/internal", response_model=list[InternalOrderOut])
def list_internal_orders(
    actor: OrderStaff,
    organization_id: str | None = Query(default=None),
    fulfilment_status: FulfilmentStatus | None = Query(default=None),
    payment_status: str | None = Query(default=None, max_length=30),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    del actor
    query = db.query(Order)
    if organization_id:
        query = query.filter(
            (Order.organization_id == organization_id) | (Order.company_id == organization_id)
        )
    if fulfilment_status:
        query = query.filter(Order.fulfilment_status == fulfilment_status.value)
    if payment_status:
        query = query.filter(Order.payment_status == payment_status.upper())
    rows = query.order_by(Order.created_at.desc(), Order.id.desc()).limit(limit).all()
    return [order_detail(row, internal=True) for row in rows]


@router.get("/internal/{order_id}", response_model=InternalOrderOut)
def get_internal_order(
    order_id: str,
    actor: OrderStaff,
    db: Session = Depends(get_db),
):
    del actor
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order_detail(order, internal=True)


@router.patch("/internal/{order_id}/fulfilment", response_model=InternalOrderOut)
def update_fulfilment(
    order_id: str,
    data: FulfilmentTransitionRequest,
    actor: OrderStaff,
    db: Session = Depends(get_db),
):
    order = (
        db.query(Order).filter(Order.id == order_id).with_for_update().one_or_none()
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        transition_order(
            db,
            order=order,
            target=data.status,
            actor=actor,
            reason=data.reason,
            customer_visible=data.customer_visible,
            expected_version=data.expected_version,
        )
        db.commit()
        db.refresh(order)
        return order_detail(order, internal=True)
    except OrderLifecycleError as exc:
        db.rollback()
        _raise_order_error(exc)


@router.get("", response_model=list[OrderSummaryOut])
def list_my_orders(
    limit: int = Query(default=100, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return [order_summary(row) for row in customer_orders(db, user, limit=limit)]


@router.get("/{order_id}/progress", response_model=CustomerOrderProgressOut)
def get_my_order_progress(
    order_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)
    if order is None or not customer_can_view(order, user, db=db):
        raise HTTPException(status_code=404, detail="Order not found")
    return customer_order_progress(db, order)


@router.post("/{order_id}/cancel", response_model=OrderDetailOut)
def cancel_my_order(
    order_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = (
        db.query(Order).filter(Order.id == order_id).with_for_update().one_or_none()
    )
    if order is None or not customer_can_view(order, user, db=db):
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        transition_order(
            db,
            order=order,
            target=FulfilmentStatus.CANCELLED,
            actor=user,
            reason="Cancelled by customer",
            customer_visible=True,
        )
        db.commit()
        db.refresh(order)
        return order_detail(order)
    except OrderLifecycleError as exc:
        db.rollback()
        _raise_order_error(exc)


@router.get("/{order_id}", response_model=OrderDetailOut)
def get_my_order(
    order_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)
    if order is None or not customer_can_view(order, user, db=db):
        raise HTTPException(status_code=404, detail="Order not found")
    return order_detail(order)


__all__ = ["router"]
