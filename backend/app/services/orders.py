"""
Order Service — DB-backed

Manages order lifecycle:
- Checkout: Cart → Order
- Payment integration
- Status transitions (check-in/check-out)
- Timeline events
- Deliverables management
"""
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

def _utcnow():
    return datetime.now(timezone.utc)


# ============ ENUMS ============

class OrderStatus(str, Enum):
    CREATED = "created"
    AWAITING_PAYMENT = "awaiting_payment"
    PAID = "paid"
    PROCESSING = "processing"
    DISPATCHED = "dispatched"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"
    PARTIALLY_REFUNDED = "partially_refunded"


class PaymentMethod(str, Enum):
    MULTICAIXA_EXPRESS = "multicaixa_express"
    VISA_MASTERCARD = "visa_mastercard"
    IBAN_ANGOLA = "iban_angola"
    IBAN_INTERNATIONAL = "iban_international"
    PAYPAL = "paypal"


# Currency → allowed payment methods
CURRENCY_PAYMENT_METHODS = {
    "AOA": [PaymentMethod.MULTICAIXA_EXPRESS, PaymentMethod.IBAN_ANGOLA],
    "USD": [PaymentMethod.VISA_MASTERCARD, PaymentMethod.IBAN_INTERNATIONAL, PaymentMethod.PAYPAL],
    "EUR": [PaymentMethod.VISA_MASTERCARD, PaymentMethod.IBAN_INTERNATIONAL, PaymentMethod.PAYPAL],
}


class EventType(str, Enum):
    ORDER_CREATED = "order_created"
    PAYMENT_INITIATED = "payment_initiated"
    PAYMENT_CONFIRMED = "payment_confirmed"
    PAYMENT_FAILED = "payment_failed"
    ORDER_PROCESSING = "order_processing"
    TEAM_ASSIGNED = "team_assigned"
    SERVICE_SCHEDULED = "service_scheduled"
    SERVICE_STARTED = "service_started"
    SERVICE_COMPLETED = "service_completed"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    DELIVERABLE_READY = "deliverable_ready"
    REFUND_INITIATED = "refund_initiated"
    REFUND_COMPLETED = "refund_completed"
    CANCELLED = "cancelled"
    NOTE_ADDED = "note_added"


# ============ DATA CLASSES (unchanged API) ============

@dataclass
class OrderItemData:
    id: str
    product_id: Optional[str]
    product_name: str
    product_type: str
    sku: Optional[str]
    quantity: int
    unit_price: int
    total_price: int
    tax_rate: float
    tax_amount: int
    status: str
    scheduled_date: Optional[datetime] = None
    custom_options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderEventData:
    id: str
    event_type: str
    title: str
    description: Optional[str]
    actor_name: Optional[str]
    is_customer_visible: bool
    created_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DeliverableData:
    id: str
    name: str
    description: Optional[str]
    deliverable_type: str
    file_size: Optional[int]
    mime_type: Optional[str]
    download_url: Optional[str]
    is_ready: bool
    created_at: datetime


@dataclass
class OrderData:
    id: str
    order_number: str
    user_id: str
    company_id: Optional[str]
    site_id: Optional[str]
    project_name: Optional[str]
    status: str
    payment_method: Optional[str]
    payment_reference: Optional[str]
    currency: str
    subtotal: int
    discount_amount: int
    coupon_code: Optional[str]
    tax_amount: int
    delivery_cost: int
    total: int
    items: List[OrderItemData]
    events: List[OrderEventData]
    deliverables: List[DeliverableData]
    delivery_method: Optional[str]
    delivery_address: Optional[Dict[str, Any]]
    assigned_team: Optional[str]
    scheduled_start: Optional[datetime]
    estimated_delivery: Optional[datetime]
    customer_notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]


@dataclass
class CheckoutResult:
    success: bool
    order_id: Optional[str] = None
    order_number: Optional[str] = None
    payment_required: bool = True
    payment_method: Optional[str] = None
    payment_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ============ ORDER SERVICE ============

class OrderService:
    """Order management service — DB-backed."""

    def __init__(self, db: Session):
        self.db = db

    def _models(self):
        from app.models import Order, OrderItem, OrderEvent, Deliverable
        return Order, OrderItem, OrderEvent, Deliverable

    def _generate_order_number(self) -> str:
        year = _utcnow().year
        # UUID-derived public references avoid the duplicate-number race of
        # selecting MAX(sequence)+1 across concurrent checkout workers.
        return f"GV-{year}-{uuid.uuid4().hex[:10].upper()}"

    def _add_event(self, order_id, event_type, title, description=None,
                   actor_name="Sistema", is_customer_visible=True, metadata=None):
        _, _, OE, _ = self._models()
        ev = OE(id=str(uuid.uuid4()), order_id=order_id, event_type=event_type,
                title=title, description=description, actor_name=actor_name,
                is_customer_visible=is_customer_visible,
                metadata_json=json.dumps(metadata or {}))
        self.db.add(ev)
        return ev

    def _transition(self, order, target, *, actor_name, reason=None) -> bool:
        from app.modules.orders.domain import OrderLifecycleError
        from app.modules.orders.services import transition_order

        try:
            transition_order(
                self.db,
                order=order,
                target=target,
                actor=None,
                actor_name=actor_name,
                reason=reason,
                customer_visible=True,
            )
            self.db.commit()
            return True
        except OrderLifecycleError:
            self.db.rollback()
            return False

    async def checkout(self, cart_id: str, user_id: Optional[str], payment_method: PaymentMethod,
                       billing_info: Optional[Dict[str, Any]] = None,
                       customer_notes: Optional[str] = None,
                       currency: Optional[str] = None,
                       organization_id: Optional[str] = None,
                       workspace_id: Optional[str] = None,
                       idempotency_key: Optional[str] = None) -> CheckoutResult:
        from app.services.cart import get_cart_service
        from app.models import CatalogItem, Payment, Product
        from app.modules.orders.domain import (
            FulfilmentStatus,
            OrderPaymentStatus,
            classify_order,
        )

        OM, OIM, _, _ = self._models()
        if idempotency_key:
            existing = (
                self.db.query(OM)
                .filter(OM.checkout_idempotency_key == idempotency_key)
                .first()
            )
            if existing:
                same_owner = str(existing.user_id or "") == str(user_id or "")
                same_organization = not organization_id or (
                    existing.organization_id or existing.company_id
                ) == organization_id
                same_currency = not currency or existing.currency == currency.upper()
                if not (same_owner and same_organization and same_currency):
                    return CheckoutResult(
                        success=False,
                        error="Idempotency key is already bound to another checkout",
                    )
                payment = (
                    self.db.get(Payment, existing.payment_intent_id)
                    if existing.payment_intent_id
                    else None
                )
                return CheckoutResult(
                    success=True,
                    order_id=existing.id,
                    order_number=existing.order_number,
                    payment_required=existing.payment_status != "NOT_REQUIRED",
                    payment_method=existing.payment_method,
                    payment_data=(
                        {
                            "payment_id": payment.id,
                            "status": payment.status,
                            "provider_reference": payment.provider_reference,
                        }
                        if payment
                        else None
                    ),
                )

        cart_svc = get_cart_service(self.db)
        cart = cart_svc.get_cart(cart_id)
        if not cart:
            return CheckoutResult(success=False, error="Carrinho não encontrado")
        if not cart.items:
            return CheckoutResult(success=False, error="Carrinho vazio")
        if cart.user_id and str(cart.user_id) != str(user_id or ""):
            return CheckoutResult(success=False, error="Carrinho não disponível")
        if cart.company_id and organization_id and cart.company_id != organization_id:
            return CheckoutResult(success=False, error="Carrinho não disponível")

        order_id = str(uuid.uuid4())
        order_number = self._generate_order_number()
        now = _utcnow()

        catalog_items = {}
        for item in cart.items:
            catalog_item = self.db.get(CatalogItem, item.product_id)
            if catalog_item is None:
                catalog_item = (
                    self.db.query(CatalogItem)
                    .filter(CatalogItem.legacy_source_id == item.product_id)
                    .first()
                )
            if catalog_item is None or catalog_item.status != "PUBLISHED":
                return CheckoutResult(success=False, error="Item do catálogo indisponível")
            catalog_items[item.product_id] = catalog_item

        effective_organization_id = organization_id or cart.company_id
        order_type = classify_order(
            catalog_items[item.product_id].item_type for item in cart.items
        ).value

        payment_reference = None
        if payment_method in [PaymentMethod.IBAN_ANGOLA, PaymentMethod.IBAN_INTERNATIONAL]:
            payment_reference = f"GV{order_number.replace('-', '')}"

        order = OM(
            id=order_id, order_number=order_number, user_id=user_id,
            company_id=effective_organization_id, site_id=cart.site_id,
            organization_id=effective_organization_id, workspace_id=workspace_id,
            order_type=order_type,
            fulfilment_status=FulfilmentStatus.CONFIRMED.value,
            payment_status=OrderPaymentStatus.PENDING.value,
            lifecycle_version=1,
            checkout_idempotency_key=idempotency_key,
            status=OrderStatus.AWAITING_PAYMENT.value, payment_method=payment_method.value,
            payment_reference=payment_reference, currency=currency or cart.currency or "EUR",
            subtotal=cart.subtotal, discount_total=cart.discount_amount,
            coupon_code=cart.coupon_code, tax_amount=cart.tax_amount,
            shipping_fee=cart.delivery_cost, total=cart.total,
            delivery_method=cart.delivery_method, customer_notes=customer_notes,
            billing_info_json=json.dumps(billing_info) if billing_info else None,
            confirmed_at=now,
            metadata_json=json.dumps(
                {"checkout": {"cart_id": cart.id, "idempotency_key_present": bool(idempotency_key)}},
                sort_keys=True,
            ),
        )
        self.db.add(order)

        for item in cart.items:
            catalog_item = catalog_items[item.product_id]
            basic_product = self.db.get(Product, item.product_id)
            oi = OIM(
                id=str(uuid.uuid4()), order_id=order_id,
                # The historical FK targets ``products`` while storefront
                # items now belong to ``catalog_items``. Do not write an
                # invalid legacy FK merely to preserve a display identifier.
                product_id=basic_product.id if basic_product else None,
                catalog_item_id=catalog_item.id,
                name=catalog_item.name,
                product_type=item.product_type,
                catalog_item_type=catalog_item.item_type,
                sku=catalog_item.code,
                currency=currency or cart.currency or "EUR",
                qty=item.quantity, unit_price=item.unit_price,
                line_total=item.total_price, tax_rate=item.tax_rate,
                tax_amount=item.tax_amount, discount_amount=0, status="pending",
                scheduled_date=item.scheduled_date,
                pricing_snapshot_json=json.dumps(
                    {
                        "catalog_item_id": catalog_item.id,
                        "code": catalog_item.code,
                        "name": catalog_item.name,
                        "item_type": catalog_item.item_type,
                        "price_model": catalog_item.price_model,
                        "currency": currency or cart.currency or "EUR",
                        "unit_amount": int(item.unit_price),
                        "quantity": item.quantity,
                        "tax_rate": float(item.tax_rate or 0),
                        "custom_options": item.custom_options,
                        "captured_at": now.isoformat(),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                fulfilment_hints_json=json.dumps(
                    {
                        "fulfilment_type": catalog_item.fulfilment_type,
                        "requires_site": catalog_item.requires_site,
                        "requires_scheduling": catalog_item.requires_scheduling,
                        "duration_hours": catalog_item.duration_hours,
                    },
                    sort_keys=True,
                ),
            )
            self.db.add(oi)

        self._add_event(order_id, EventType.ORDER_CREATED.value,
                        "Pedido criado", f"Pedido {order_number} criado com sucesso.")

        self.db.flush()

        # Order, line snapshots, ERP outbox command, and its wake-up event are
        # committed atomically by the checkout transaction. ERP availability
        # is never part of the customer-facing checkout result.
        from app.modules.orders.services import enqueue_order_created_erp

        enqueue_order_created_erp(self.db, order=order)

        # Decrement stock for items that track inventory
        try:
            from sqlalchemy import text as sa_text
            with self.db.begin_nested():
                for item in cart.items:
                    result = self.db.execute(
                        sa_text("""UPDATE shop_products
                                   SET stock_quantity = stock_quantity - :qty,
                                       updated_at = :now
                                   WHERE id = :pid AND track_inventory = true
                                     AND stock_quantity >= :qty"""),
                        {"qty": item.quantity, "now": now, "pid": item.product_id}
                    )
                    if result.rowcount > 0:
                        logger.info(f"Stock decremented: product {item.product_id} by {item.quantity}")
        except Exception as e:
            logger.warning("Stock decrement failed (%s)", type(e).__name__)

        payment_data = await self._initiate_payment(order, payment_method)

        self._add_event(order_id, EventType.PAYMENT_INITIATED.value,
                        "Aguardando pagamento",
                        f"Pagamento via {payment_method.value} iniciado.",
                        metadata=payment_data or {})

        if payment_data:
            order.payment_intent_id = payment_data.get("payment_id")
            order.payment_reference = payment_data.get("provider_reference") or order.payment_reference

        cart_svc.clear_cart(cart_id)
        self.db.commit()
        logger.info(f"Checkout completed: order {order_number}, payment {payment_method.value}")

        return CheckoutResult(
            success=True, order_id=order_id, order_number=order_number,
            payment_required=True, payment_method=payment_method.value,
            payment_data=payment_data,
        )

    async def _initiate_payment(self, order, payment_method: PaymentMethod):
        from app.services.payments import get_payment_orchestrator, PaymentProvider, Currency
        orchestrator = get_payment_orchestrator(self.db)
        provider_map = {
            PaymentMethod.MULTICAIXA_EXPRESS: PaymentProvider.MULTICAIXA_EXPRESS,
            PaymentMethod.VISA_MASTERCARD: PaymentProvider.VISA_MASTERCARD,
            PaymentMethod.IBAN_ANGOLA: PaymentProvider.IBAN_TRANSFER,
            PaymentMethod.IBAN_INTERNATIONAL: PaymentProvider.IBAN_TRANSFER,
            PaymentMethod.PAYPAL: PaymentProvider.PAYPAL,
        }
        provider = provider_map.get(payment_method)
        if not provider:
            return None
        # Preserve an explicit order currency; Spain-first checkouts default to EUR.
        try:
            order_currency = Currency(order.currency or "EUR")
        except ValueError:
            order_currency = Currency.EUR
        result = await orchestrator.create_payment(
            company_id=order.company_id or "default",
            # Orders currently use a Numeric column while payments store the
            # smallest currency unit as an Integer. Normalise explicitly so
            # SQLite and PostgreSQL receive the same contract.
            order_id=order.id, amount=int(order.total),
            currency=order_currency, provider=provider,
            description=f"Pedido {order.order_number}",
            idempotency_key=f"order-{order.id}",
        )
        return {
            "success": result.success,
            "payment_id": result.payment_id, "status": result.status.value,
            "provider_reference": result.provider_reference,
            "client_secret": result.client_secret,
            "qr_code": result.qr_code, "redirect_url": result.redirect_url,
            "transfer_details": result.raw_response.get("transfer_details") if result.raw_response else None,
            "error_code": result.error_code,
            "error_message": result.error_message,
        }

    async def confirm_payment(self, order_id: str, payment_reference=None, confirmed_by=None) -> bool:
        from app.models import Payment
        from app.modules.orders.domain import FulfilmentStatus, OrderPaymentStatus
        from app.modules.orders.services import apply_payment_state
        from app.services.payments import PaymentStatus

        OM = self._models()[0]
        order = self.db.get(OM, order_id)
        if not order:
            return False
        now = _utcnow()
        if payment_reference:
            order.payment_reference = payment_reference
        payment = (
            self.db.get(Payment, order.payment_intent_id)
            if order.payment_intent_id
            else self.db.query(Payment).filter(Payment.order_id == order.id).first()
        )
        if payment is not None:
            payment.status = PaymentStatus.COMPLETED.value
            payment.completed_at = payment.completed_at or now
            payment.updated_at = now
            if payment_reference:
                payment.provider_reference = payment_reference
            apply_payment_state(
                self.db,
                payment=payment,
                provider_status=PaymentStatus.COMPLETED.value,
                actor_name=confirmed_by or "GeoVision finance",
            )
        else:
            order.payment_status = OrderPaymentStatus.PAID.value
            order.payment_confirmed_at = now
            order.updated_at = now
            if order.fulfilment_status in {
                FulfilmentStatus.CONFIRMED.value,
                FulfilmentStatus.PAYMENT_AUTHORIZED.value,
            }:
                order.previous_fulfilment_status = order.fulfilment_status
                order.fulfilment_status = FulfilmentStatus.PAID.value
                order.status = OrderStatus.PAID.value
            order.lifecycle_version = int(order.lifecycle_version or 0) + 1
            self._add_event(
                order_id,
                EventType.PAYMENT_CONFIRMED.value,
                "Pagamento confirmado",
                "O pagamento foi confirmado com sucesso.",
                actor_name=confirmed_by or "Sistema",
                metadata={"reference": payment_reference},
            )
        self.db.commit()
        return True

    async def start_processing(self, order_id: str) -> bool:
        from app.modules.orders.domain import FulfilmentStatus

        OM = self._models()[0]
        order = self.db.get(OM, order_id)
        if not order:
            return False
        return self._transition(
            order,
            FulfilmentStatus.PROCESSING,
            actor_name="Sistema",
        )

    async def assign_team(self, order_id: str, team_name: str,
                          scheduled_start=None, scheduled_end=None, assigned_by=None) -> bool:
        from app.modules.orders.domain import FulfilmentStatus, OrderLifecycleError
        from app.modules.orders.services import transition_order

        OM = self._models()[0]
        order = self.db.get(OM, order_id)
        if not order:
            return False
        try:
            transition_order(
                self.db,
                order=order,
                target=FulfilmentStatus.ASSIGNED,
                actor=None,
                actor_name=assigned_by or "GeoVision operations",
                customer_visible=True,
            )
            order.assigned_team = team_name
            order.scheduled_start = scheduled_start
            order.scheduled_end = scheduled_end
            self.db.commit()
            return True
        except OrderLifecycleError:
            self.db.rollback()
            return False

    async def start_service(self, order_id: str, started_by=None) -> bool:
        from app.modules.orders.domain import FulfilmentStatus

        OM = self._models()[0]
        order = self.db.get(OM, order_id)
        if not order:
            return False
        return self._transition(
            order,
            FulfilmentStatus.IN_PROGRESS,
            actor_name=started_by or "GeoVision operations",
        )

    async def complete_service(self, order_id: str, completed_by=None, notes=None) -> bool:
        from app.modules.orders.domain import FulfilmentStatus

        OM = self._models()[0]
        order = self.db.get(OM, order_id)
        if not order:
            return False
        if notes:
            order.internal_notes = (order.internal_notes or "") + f"\n{notes}"
        return self._transition(
            order,
            FulfilmentStatus.COMPLETED,
            actor_name=completed_by or "GeoVision operations",
        )

    async def ship_order(self, order_id: str, tracking_number=None, carrier=None) -> bool:
        from app.modules.orders.domain import FulfilmentStatus

        OM = self._models()[0]
        order = self.db.get(OM, order_id)
        if not order:
            return False
        metadata = json.loads(order.metadata_json or "{}")
        metadata["shipment"] = {"tracking": tracking_number, "carrier": carrier}
        order.metadata_json = json.dumps(metadata, sort_keys=True)
        return self._transition(
            order,
            FulfilmentStatus.IN_PROGRESS,
            actor_name="GeoVision logistics",
        )

    async def deliver_order(self, order_id: str, delivered_by=None) -> bool:
        from app.modules.orders.domain import FulfilmentStatus

        OM = self._models()[0]
        order = self.db.get(OM, order_id)
        if not order:
            return False
        return self._transition(
            order,
            FulfilmentStatus.DELIVERED,
            actor_name=delivered_by or "GeoVision logistics",
        )

    async def add_deliverable(self, order_id: str, name: str, deliverable_type: str,
                              storage_key=None, download_url=None,
                              file_size=None, mime_type=None, description=None):
        OM = self._models()[0]
        _, _, _, DM = self._models()
        order = self.db.get(OM, order_id)
        if not order:
            return None
        did = str(uuid.uuid4())
        d = DM(id=did, order_id=order_id, name=name, deliverable_type=deliverable_type,
               storage_key=storage_key, download_url=download_url,
               file_size=file_size, is_ready=True)
        self.db.add(d)
        order.updated_at = _utcnow()
        self._add_event(order_id, EventType.DELIVERABLE_READY.value,
                        "Ficheiro disponível", f"O ficheiro '{name}' está pronto para download.",
                        metadata={"deliverable_id": did, "name": name})
        self.db.commit()
        return did

    async def cancel_order(self, order_id: str, reason=None, cancelled_by=None) -> bool:
        from app.modules.orders.domain import FulfilmentStatus

        OM = self._models()[0]
        order = self.db.get(OM, order_id)
        if not order:
            return False
        return self._transition(
            order,
            FulfilmentStatus.CANCELLED,
            actor_name=cancelled_by or "Sistema",
            reason=reason or "O pedido foi cancelado.",
        )

    def get_order(self, order_id: str) -> Optional[OrderData]:
        OM = self._models()[0]
        order = self.db.get(OM, order_id)
        return self._to_data(order) if order else None

    def get_order_by_number(self, order_number: str) -> Optional[OrderData]:
        OM = self._models()[0]
        order = self.db.query(OM).filter(OM.order_number == order_number).first()
        return self._to_data(order) if order else None

    def list_orders(self, user_id=None, company_id=None, site_id=None,
                    status=None, limit=50) -> List[OrderData]:
        OM = self._models()[0]
        q = self.db.query(OM)
        if user_id:
            q = q.filter(OM.user_id == user_id)
        if company_id:
            q = q.filter(OM.company_id == company_id)
        if site_id:
            q = q.filter(OM.site_id == site_id)
        if status:
            q = q.filter(OM.status == status)
        q = q.order_by(OM.created_at.desc()).limit(limit)
        return [self._to_data(o) for o in q.all()]

    def _to_data(self, order) -> OrderData:
        items = [OrderItemData(
            id=i.id, product_id=getattr(i, 'catalog_item_id', None) or i.product_id,
            product_name=i.name,
            product_type=getattr(i, 'catalog_item_type', None) or getattr(i, 'product_type', None), sku=i.sku, quantity=i.qty,
            unit_price=i.unit_price, total_price=i.line_total,
            tax_rate=float(i.tax_rate or 0), tax_amount=getattr(i, 'tax_amount', 0) or 0,
            status=getattr(i, 'status', None) or "pending", scheduled_date=getattr(i, 'scheduled_date', None))
            for i in order.items]
        events = [OrderEventData(
            id=e.id, event_type=e.event_type, title=e.title,
            description=e.description, actor_name=e.actor_name,
            is_customer_visible=e.is_customer_visible, created_at=e.created_at,
            metadata=json.loads(e.metadata_json or "{}"))
            for e in (order.events_rel or [])]
        deliverables = [DeliverableData(
            id=d.id, name=d.name, description=None,
            deliverable_type=d.deliverable_type, file_size=d.file_size,
            mime_type=None, download_url=d.download_url,
            is_ready=d.is_ready, created_at=d.created_at)
            for d in (order.deliverables_rel or [])]
        return OrderData(
            id=order.id, order_number=order.order_number, user_id=order.user_id,
            company_id=getattr(order, 'company_id', None), site_id=getattr(order, 'site_id', None),
            project_name=None, status=order.status,
            payment_method=order.payment_method, payment_reference=order.payment_reference,
            currency=order.currency or "EUR", subtotal=order.subtotal,
            discount_amount=order.discount_total or 0, coupon_code=order.coupon_code,
            tax_amount=order.tax_amount or 0, delivery_cost=order.shipping_fee or 0,
            total=order.total, items=items, events=events, deliverables=deliverables,
            delivery_method=order.delivery_method, delivery_address=None,
            assigned_team=order.assigned_team, scheduled_start=order.scheduled_start,
            estimated_delivery=order.estimated_delivery, customer_notes=order.customer_notes,
            created_at=order.created_at, updated_at=order.updated_at,
            completed_at=order.completed_at)


def get_order_service(db: Session) -> OrderService:
    """Get order service instance (requires db session)."""
    return OrderService(db)
