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
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy.orm import Session
from sqlalchemy import func

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
    product_id: str
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
        OM = self._models()[0]
        year = _utcnow().year
        prefix = f"GV-{year}-"
        last = (self.db.query(OM.order_number)
                .filter(OM.order_number.like(f"{prefix}%"))
                .order_by(OM.order_number.desc()).first())
        if last and last[0]:
            try:
                seq = int(last[0].split("-")[-1]) + 1
            except ValueError:
                seq = 1
        else:
            seq = 1
        return f"{prefix}{seq:06d}"

    def _add_event(self, order_id, event_type, title, description=None,
                   actor_name="Sistema", is_customer_visible=True, metadata=None):
        _, _, OE, _ = self._models()
        ev = OE(id=str(uuid.uuid4()), order_id=order_id, event_type=event_type,
                title=title, description=description, actor_name=actor_name,
                is_customer_visible=is_customer_visible,
                metadata_json=json.dumps(metadata or {}))
        self.db.add(ev)
        return ev

    async def checkout(self, cart_id: str, user_id: str, payment_method: PaymentMethod,
                       billing_info: Optional[Dict[str, Any]] = None,
                       customer_notes: Optional[str] = None,
                       currency: Optional[str] = None) -> CheckoutResult:
        from app.services.cart import get_cart_service
        from app.services.payments import get_payment_orchestrator, PaymentProvider, Currency

        cart_svc = get_cart_service(self.db)
        cart = cart_svc.get_cart(cart_id)
        if not cart:
            return CheckoutResult(success=False, error="Carrinho não encontrado")
        if not cart.items:
            return CheckoutResult(success=False, error="Carrinho vazio")

        OM, OIM, _, _ = self._models()
        order_id = str(uuid.uuid4())
        order_number = self._generate_order_number()
        now = _utcnow()

        payment_reference = None
        if payment_method in [PaymentMethod.IBAN_ANGOLA, PaymentMethod.IBAN_INTERNATIONAL]:
            payment_reference = f"GV{order_number.replace('-', '')}"

        order = OM(
            id=order_id, order_number=order_number, user_id=user_id,
            company_id=cart.company_id, site_id=cart.site_id,
            status=OrderStatus.CREATED.value, payment_method=payment_method.value,
            payment_reference=payment_reference, currency=currency or cart.currency or "AOA",
            subtotal=cart.subtotal, discount_total=cart.discount_amount,
            coupon_code=cart.coupon_code, tax_amount=cart.tax_amount,
            shipping_fee=cart.delivery_cost, total=cart.total,
            delivery_method=cart.delivery_method, customer_notes=customer_notes,
            billing_info_json=json.dumps(billing_info) if billing_info else None,
        )
        self.db.add(order)

        for item in cart.items:
            oi = OIM(
                id=str(uuid.uuid4()), order_id=order_id,
                product_id=item.product_id, name=item.product_name,
                product_type=item.product_type, sku=item.sku,
                qty=item.quantity, unit_price=item.unit_price,
                line_total=item.total_price, tax_rate=item.tax_rate,
                tax_amount=item.tax_amount, status="pending",
                scheduled_date=item.scheduled_date,
            )
            self.db.add(oi)

        self._add_event(order_id, EventType.ORDER_CREATED.value,
                        "Pedido criado", f"Pedido {order_number} criado com sucesso.")

        self.db.flush()

        # Decrement stock for items that track inventory
        try:
            from sqlalchemy import text as sa_text
            for item in cart.items:
                result = self.db.execute(
                    sa_text("""UPDATE shop_products
                               SET stock_quantity = stock_quantity - :qty,
                                   updated_at = :now
                               WHERE id = :pid AND track_inventory = true
                                 AND stock_quantity >= :qty"""),
                    {"qty": item.quantity, "now": now.isoformat(), "pid": item.product_id}
                )
                if result.rowcount > 0:
                    logger.info(f"Stock decremented: product {item.product_id} by {item.quantity}")
        except Exception as e:
            logger.warning(f"Stock decrement failed (non-critical): {e}")

        cart_svc.clear_cart(cart_id)

        payment_data = await self._initiate_payment(order, payment_method)

        order.status = OrderStatus.AWAITING_PAYMENT.value
        self._add_event(order_id, EventType.PAYMENT_INITIATED.value,
                        "Aguardando pagamento",
                        f"Pagamento via {payment_method.value} iniciado.",
                        metadata=payment_data or {})

        if payment_data:
            order.payment_intent_id = payment_data.get("payment_id")

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
        # Use the order's currency instead of hardcoded AOA
        try:
            order_currency = Currency(order.currency or "AOA")
        except ValueError:
            order_currency = Currency.AOA
        result = await orchestrator.create_payment(
            company_id=order.company_id or "default",
            order_id=order.id, amount=order.total,
            currency=order_currency, provider=provider,
            description=f"Pedido {order.order_number}",
            idempotency_key=f"order-{order.id}",
        )
        return {
            "payment_id": result.payment_id, "status": result.status.value,
            "provider_reference": result.provider_reference,
            "client_secret": result.client_secret,
            "qr_code": result.qr_code, "redirect_url": result.redirect_url,
            "transfer_details": result.raw_response.get("transfer_details") if result.raw_response else None,
        }

    async def confirm_payment(self, order_id: str, payment_reference=None, confirmed_by=None) -> bool:
        OM = self._models()[0]
        order = self.db.get(OM, order_id)
        if not order:
            return False
        now = _utcnow()
        order.status = OrderStatus.PAID.value
        order.payment_confirmed_at = now
        order.updated_at = now
        if payment_reference:
            order.payment_reference = payment_reference
        self._add_event(order_id, EventType.PAYMENT_CONFIRMED.value,
                        "Pagamento confirmado", "O pagamento foi confirmado com sucesso.",
                        actor_name=confirmed_by or "Sistema",
                        metadata={"reference": payment_reference})
        self.db.commit()
        await self.start_processing(order_id)
        return True

    async def start_processing(self, order_id: str) -> bool:
        OM = self._models()[0]
        order = self.db.get(OM, order_id)
        if not order:
            return False
        order.status = OrderStatus.PROCESSING.value
        order.updated_at = _utcnow()
        self._add_event(order_id, EventType.ORDER_PROCESSING.value,
                        "Em processamento", "O seu pedido está a ser processado.")
        self.db.commit()
        return True

    async def assign_team(self, order_id: str, team_name: str,
                          scheduled_start=None, scheduled_end=None, assigned_by=None) -> bool:
        OM = self._models()[0]
        order = self.db.get(OM, order_id)
        if not order:
            return False
        now = _utcnow()
        order.status = OrderStatus.ASSIGNED.value
        order.assigned_team = team_name
        order.scheduled_start = scheduled_start
        order.scheduled_end = scheduled_end
        order.updated_at = now
        self._add_event(order_id, EventType.TEAM_ASSIGNED.value,
                        "Equipa atribuída", f"Equipa {team_name} foi atribuída ao seu pedido.",
                        actor_name=assigned_by or "Admin", metadata={"team": team_name})
        if scheduled_start:
            self._add_event(order_id, EventType.SERVICE_SCHEDULED.value,
                            "Serviço agendado",
                            f"Agendado para {scheduled_start.strftime('%d/%m/%Y %H:%M')}.",
                            metadata={"scheduled_start": scheduled_start.isoformat()})
        self.db.commit()
        return True

    async def start_service(self, order_id: str, started_by=None) -> bool:
        OM = self._models()[0]
        order = self.db.get(OM, order_id)
        if not order:
            return False
        now = _utcnow()
        order.status = OrderStatus.IN_PROGRESS.value
        order.actual_start = now
        order.updated_at = now
        self._add_event(order_id, EventType.SERVICE_STARTED.value,
                        "Serviço iniciado", "A equipa iniciou o serviço.",
                        actor_name=started_by or "Equipa")
        self.db.commit()
        return True

    async def complete_service(self, order_id: str, completed_by=None, notes=None) -> bool:
        OM = self._models()[0]
        order = self.db.get(OM, order_id)
        if not order:
            return False
        now = _utcnow()
        order.status = OrderStatus.COMPLETED.value
        order.actual_end = now
        order.completed_at = now
        order.updated_at = now
        if notes:
            order.internal_notes = (order.internal_notes or "") + f"\n{notes}"
        self._add_event(order_id, EventType.SERVICE_COMPLETED.value,
                        "Serviço concluído", "O serviço foi concluído com sucesso.",
                        actor_name=completed_by or "Equipa", metadata={"notes": notes})
        self.db.commit()
        logger.info(f"Service completed for order {order.order_number}")
        return True

    async def ship_order(self, order_id: str, tracking_number=None, carrier=None) -> bool:
        OM = self._models()[0]
        order = self.db.get(OM, order_id)
        if not order:
            return False
        now = _utcnow()
        order.status = OrderStatus.DISPATCHED.value
        order.updated_at = now
        desc = "O seu pedido foi enviado."
        if tracking_number:
            desc += f" Código de rastreio: {tracking_number}"
        self._add_event(order_id, EventType.SHIPPED.value,
                        "Pedido enviado", desc,
                        metadata={"tracking": tracking_number, "carrier": carrier})
        self.db.commit()
        return True

    async def deliver_order(self, order_id: str, delivered_by=None) -> bool:
        OM = self._models()[0]
        order = self.db.get(OM, order_id)
        if not order:
            return False
        now = _utcnow()
        order.status = OrderStatus.DELIVERED.value
        order.actual_delivery = now
        order.completed_at = now
        order.updated_at = now
        self._add_event(order_id, EventType.DELIVERED.value,
                        "Pedido entregue", "O seu pedido foi entregue com sucesso.",
                        actor_name=delivered_by or "Transportadora")
        self.db.commit()
        return True

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
        OM = self._models()[0]
        order = self.db.get(OM, order_id)
        if not order:
            return False
        if order.status in [OrderStatus.COMPLETED.value, OrderStatus.DELIVERED.value]:
            return False
        now = _utcnow()
        order.status = OrderStatus.CANCELLED.value
        order.cancelled_at = now
        order.updated_at = now
        self._add_event(order_id, EventType.CANCELLED.value,
                        "Pedido cancelado", reason or "O pedido foi cancelado.",
                        actor_name=cancelled_by or "Sistema", metadata={"reason": reason})
        self.db.commit()
        return True

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
            id=i.id, product_id=i.product_id, product_name=i.name,
            product_type=getattr(i, 'product_type', None), sku=i.sku, quantity=i.qty,
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
            currency=order.currency or "AOA", subtotal=order.subtotal,
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
