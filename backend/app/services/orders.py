"""
Order Service

Manages order lifecycle:
- Checkout: Cart → Order
- Payment integration
- Status transitions (check-in/check-out)
- Timeline events
- Deliverables management
"""
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from app.services.cart import get_cart_service, CartData
from app.services.payments import get_payment_orchestrator, PaymentProvider, Currency

logger = logging.getLogger(__name__)


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


# ============ DATA CLASSES ============

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


# ============ IN-MEMORY STORES ============

_orders_store: Dict[str, dict] = {}
_order_counter = 0


def _generate_order_number() -> str:
    """Generate unique order number."""
    global _order_counter
    _order_counter += 1
    year = datetime.utcnow().year
    return f"GV-{year}-{_order_counter:06d}"


# ============ ORDER SERVICE ============

class OrderService:
    """Order management service."""
    
    async def checkout(
        self,
        cart_id: str,
        user_id: str,
        payment_method: PaymentMethod,
        billing_info: Optional[Dict[str, Any]] = None,
        customer_notes: Optional[str] = None,
    ) -> CheckoutResult:
        """
        Convert cart to order and initiate payment.
        
        This is the "check-in" process.
        """
        
        cart_service = get_cart_service()
        cart = cart_service.get_cart(cart_id)
        
        if not cart:
            return CheckoutResult(success=False, error="Carrinho não encontrado")
        
        if not cart.items:
            return CheckoutResult(success=False, error="Carrinho vazio")
        
        # Create order
        order_id = str(uuid.uuid4())
        order_number = _generate_order_number()
        now = datetime.utcnow()
        
        # Convert cart items to order items
        items = []
        for item in cart.items:
            order_item = {
                "id": str(uuid.uuid4()),
                "product_id": item.product_id,
                "product_name": item.product_name,
                "product_type": item.product_type,
                "sku": item.sku,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "total_price": item.total_price,
                "tax_rate": item.tax_rate,
                "tax_amount": item.tax_amount,
                "scheduled_date": item.scheduled_date,
                "custom_options": item.custom_options,
                "status": "pending",
            }
            items.append(order_item)
        
        # Generate payment reference for IBAN
        payment_reference = None
        if payment_method in [PaymentMethod.IBAN_ANGOLA, PaymentMethod.IBAN_INTERNATIONAL]:
            payment_reference = f"GV{order_number.replace('-', '')}"
        
        order = {
            "id": order_id,
            "order_number": order_number,
            "user_id": user_id,
            "company_id": cart.company_id,
            "site_id": cart.site_id,
            "project_name": None,
            "status": OrderStatus.CREATED.value,
            "payment_method": payment_method.value,
            "payment_intent_id": None,
            "payment_reference": payment_reference,
            "payment_confirmed_at": None,
            "currency": cart.currency,
            "subtotal": cart.subtotal,
            "discount_amount": cart.discount_amount,
            "coupon_code": cart.coupon_code,
            "tax_amount": cart.tax_amount,
            "delivery_cost": cart.delivery_cost,
            "total": cart.total,
            "items": items,
            "events": [],
            "deliverables": [],
            "invoices": [],
            "delivery_method": cart.delivery_method,
            "delivery_address": None,  # From billing_info
            "delivery_notes": None,
            "estimated_delivery": None,
            "actual_delivery": None,
            "assigned_team": None,
            "scheduled_start": None,
            "scheduled_end": None,
            "actual_start": None,
            "actual_end": None,
            "customer_notes": customer_notes,
            "internal_notes": None,
            "billing_info": billing_info,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
            "cancelled_at": None,
            "metadata": {},
        }
        
        # Add creation event
        order["events"].append({
            "id": str(uuid.uuid4()),
            "event_type": EventType.ORDER_CREATED.value,
            "title": "Pedido criado",
            "description": f"Pedido {order_number} criado com sucesso.",
            "actor_name": "Sistema",
            "is_customer_visible": True,
            "metadata": {},
            "created_at": now,
        })
        
        _orders_store[order_id] = order
        
        # Clear cart
        cart_service.clear_cart(cart_id)
        
        # Initiate payment
        payment_data = await self._initiate_payment(order, payment_method)
        
        # Update order status
        order["status"] = OrderStatus.AWAITING_PAYMENT.value
        order["events"].append({
            "id": str(uuid.uuid4()),
            "event_type": EventType.PAYMENT_INITIATED.value,
            "title": "Aguardando pagamento",
            "description": f"Pagamento via {payment_method.value} iniciado.",
            "actor_name": "Sistema",
            "is_customer_visible": True,
            "metadata": payment_data or {},
            "created_at": datetime.utcnow(),
        })
        
        if payment_data:
            order["payment_intent_id"] = payment_data.get("payment_id")
        
        logger.info(f"Checkout completed: order {order_number}, payment {payment_method.value}")
        
        return CheckoutResult(
            success=True,
            order_id=order_id,
            order_number=order_number,
            payment_required=True,
            payment_method=payment_method.value,
            payment_data=payment_data,
        )
    
    async def _initiate_payment(
        self,
        order: dict,
        payment_method: PaymentMethod
    ) -> Optional[Dict[str, Any]]:
        """Initiate payment with orchestrator."""
        
        orchestrator = get_payment_orchestrator()
        
        # Map payment method to provider
        provider_map = {
            PaymentMethod.MULTICAIXA_EXPRESS: PaymentProvider.MULTICAIXA_EXPRESS,
            PaymentMethod.VISA_MASTERCARD: PaymentProvider.VISA_MASTERCARD,
            PaymentMethod.IBAN_ANGOLA: PaymentProvider.IBAN_TRANSFER,
            PaymentMethod.IBAN_INTERNATIONAL: PaymentProvider.IBAN_TRANSFER,
        }
        
        provider = provider_map.get(payment_method)
        if not provider:
            return None
        
        result = await orchestrator.create_payment(
            company_id=order.get("company_id") or "default",
            order_id=order["id"],
            amount=order["total"],
            currency=Currency.AOA,
            provider=provider,
            description=f"Pedido {order['order_number']}",
            idempotency_key=f"order-{order['id']}",
        )
        
        return {
            "payment_id": result.payment_id,
            "status": result.status.value,
            "provider_reference": result.provider_reference,
            "qr_code": result.qr_code,
            "redirect_url": result.redirect_url,
            "transfer_details": result.raw_response.get("transfer_details") if result.raw_response else None,
        }
    
    async def confirm_payment(
        self,
        order_id: str,
        payment_reference: Optional[str] = None,
        confirmed_by: Optional[str] = None,
    ) -> bool:
        """
        Confirm payment for an order.
        
        Called by webhook or admin for IBAN confirmation.
        """
        
        order = _orders_store.get(order_id)
        if not order:
            return False
        
        now = datetime.utcnow()
        
        order["status"] = OrderStatus.PAID.value
        order["payment_confirmed_at"] = now
        order["updated_at"] = now
        
        if payment_reference:
            order["payment_reference"] = payment_reference
        
        # Add event
        order["events"].append({
            "id": str(uuid.uuid4()),
            "event_type": EventType.PAYMENT_CONFIRMED.value,
            "title": "Pagamento confirmado",
            "description": "O pagamento foi confirmado com sucesso.",
            "actor_name": confirmed_by or "Sistema",
            "is_customer_visible": True,
            "metadata": {"reference": payment_reference},
            "created_at": now,
        })
        
        logger.info(f"Payment confirmed for order {order['order_number']}")
        
        # Auto-transition to processing
        await self.start_processing(order_id)
        
        return True
    
    async def start_processing(self, order_id: str) -> bool:
        """Start processing the order."""
        
        order = _orders_store.get(order_id)
        if not order:
            return False
        
        now = datetime.utcnow()
        
        order["status"] = OrderStatus.PROCESSING.value
        order["updated_at"] = now
        
        order["events"].append({
            "id": str(uuid.uuid4()),
            "event_type": EventType.ORDER_PROCESSING.value,
            "title": "Em processamento",
            "description": "O seu pedido está a ser processado.",
            "actor_name": "Sistema",
            "is_customer_visible": True,
            "metadata": {},
            "created_at": now,
        })
        
        return True
    
    async def assign_team(
        self,
        order_id: str,
        team_name: str,
        scheduled_start: Optional[datetime] = None,
        scheduled_end: Optional[datetime] = None,
        assigned_by: Optional[str] = None,
    ) -> bool:
        """Assign team for service execution."""
        
        order = _orders_store.get(order_id)
        if not order:
            return False
        
        now = datetime.utcnow()
        
        order["status"] = OrderStatus.ASSIGNED.value
        order["assigned_team"] = team_name
        order["scheduled_start"] = scheduled_start
        order["scheduled_end"] = scheduled_end
        order["updated_at"] = now
        
        order["events"].append({
            "id": str(uuid.uuid4()),
            "event_type": EventType.TEAM_ASSIGNED.value,
            "title": "Equipa atribuída",
            "description": f"Equipa {team_name} foi atribuída ao seu pedido.",
            "actor_name": assigned_by or "Admin",
            "is_customer_visible": True,
            "metadata": {"team": team_name},
            "created_at": now,
        })
        
        if scheduled_start:
            order["events"].append({
                "id": str(uuid.uuid4()),
                "event_type": EventType.SERVICE_SCHEDULED.value,
                "title": "Serviço agendado",
                "description": f"Agendado para {scheduled_start.strftime('%d/%m/%Y %H:%M')}.",
                "actor_name": "Sistema",
                "is_customer_visible": True,
                "metadata": {"scheduled_start": scheduled_start.isoformat()},
                "created_at": now,
            })
        
        return True
    
    async def start_service(self, order_id: str, started_by: Optional[str] = None) -> bool:
        """Mark service as started (check-in field)."""
        
        order = _orders_store.get(order_id)
        if not order:
            return False
        
        now = datetime.utcnow()
        
        order["status"] = OrderStatus.IN_PROGRESS.value
        order["actual_start"] = now
        order["updated_at"] = now
        
        order["events"].append({
            "id": str(uuid.uuid4()),
            "event_type": EventType.SERVICE_STARTED.value,
            "title": "Serviço iniciado",
            "description": "A equipa iniciou o serviço.",
            "actor_name": started_by or "Equipa",
            "is_customer_visible": True,
            "metadata": {},
            "created_at": now,
        })
        
        return True
    
    async def complete_service(
        self,
        order_id: str,
        completed_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """
        Mark service as completed (check-out).
        
        This is the delivery confirmation for services.
        """
        
        order = _orders_store.get(order_id)
        if not order:
            return False
        
        now = datetime.utcnow()
        
        order["status"] = OrderStatus.COMPLETED.value
        order["actual_end"] = now
        order["completed_at"] = now
        order["updated_at"] = now
        
        if notes:
            order["internal_notes"] = (order.get("internal_notes") or "") + f"\n{notes}"
        
        order["events"].append({
            "id": str(uuid.uuid4()),
            "event_type": EventType.SERVICE_COMPLETED.value,
            "title": "Serviço concluído",
            "description": "O serviço foi concluído com sucesso.",
            "actor_name": completed_by or "Equipa",
            "is_customer_visible": True,
            "metadata": {"notes": notes},
            "created_at": now,
        })
        
        logger.info(f"Service completed for order {order['order_number']}")
        
        return True
    
    async def ship_order(
        self,
        order_id: str,
        tracking_number: Optional[str] = None,
        carrier: Optional[str] = None,
    ) -> bool:
        """Mark physical order as shipped."""
        
        order = _orders_store.get(order_id)
        if not order:
            return False
        
        now = datetime.utcnow()
        
        order["status"] = OrderStatus.DISPATCHED.value
        order["updated_at"] = now
        
        description = "O seu pedido foi enviado."
        if tracking_number:
            description += f" Código de rastreio: {tracking_number}"
        
        order["events"].append({
            "id": str(uuid.uuid4()),
            "event_type": EventType.SHIPPED.value,
            "title": "Pedido enviado",
            "description": description,
            "actor_name": "Sistema",
            "is_customer_visible": True,
            "metadata": {"tracking": tracking_number, "carrier": carrier},
            "created_at": now,
        })
        
        return True
    
    async def deliver_order(self, order_id: str, delivered_by: Optional[str] = None) -> bool:
        """Mark order as delivered (physical products)."""
        
        order = _orders_store.get(order_id)
        if not order:
            return False
        
        now = datetime.utcnow()
        
        order["status"] = OrderStatus.DELIVERED.value
        order["actual_delivery"] = now
        order["completed_at"] = now
        order["updated_at"] = now
        
        order["events"].append({
            "id": str(uuid.uuid4()),
            "event_type": EventType.DELIVERED.value,
            "title": "Pedido entregue",
            "description": "O seu pedido foi entregue com sucesso.",
            "actor_name": delivered_by or "Transportadora",
            "is_customer_visible": True,
            "metadata": {},
            "created_at": now,
        })
        
        return True
    
    async def add_deliverable(
        self,
        order_id: str,
        name: str,
        deliverable_type: str,
        storage_key: Optional[str] = None,
        download_url: Optional[str] = None,
        file_size: Optional[int] = None,
        mime_type: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[str]:
        """Add a deliverable file to the order."""
        
        order = _orders_store.get(order_id)
        if not order:
            return None
        
        now = datetime.utcnow()
        deliverable_id = str(uuid.uuid4())
        
        deliverable = {
            "id": deliverable_id,
            "order_item_id": None,
            "name": name,
            "description": description,
            "deliverable_type": deliverable_type,
            "storage_key": storage_key,
            "download_url": download_url,
            "file_size": file_size,
            "mime_type": mime_type,
            "download_count": 0,
            "is_ready": True,
            "generated_at": now,
            "created_at": now,
        }
        
        order["deliverables"].append(deliverable)
        order["updated_at"] = now
        
        order["events"].append({
            "id": str(uuid.uuid4()),
            "event_type": EventType.DELIVERABLE_READY.value,
            "title": "Ficheiro disponível",
            "description": f"O ficheiro '{name}' está pronto para download.",
            "actor_name": "Sistema",
            "is_customer_visible": True,
            "metadata": {"deliverable_id": deliverable_id, "name": name},
            "created_at": now,
        })
        
        return deliverable_id
    
    async def cancel_order(
        self,
        order_id: str,
        reason: Optional[str] = None,
        cancelled_by: Optional[str] = None,
    ) -> bool:
        """Cancel an order."""
        
        order = _orders_store.get(order_id)
        if not order:
            return False
        
        # Can only cancel if not completed
        if order["status"] in [OrderStatus.COMPLETED.value, OrderStatus.DELIVERED.value]:
            return False
        
        now = datetime.utcnow()
        
        order["status"] = OrderStatus.CANCELLED.value
        order["cancelled_at"] = now
        order["updated_at"] = now
        
        order["events"].append({
            "id": str(uuid.uuid4()),
            "event_type": EventType.CANCELLED.value,
            "title": "Pedido cancelado",
            "description": reason or "O pedido foi cancelado.",
            "actor_name": cancelled_by or "Sistema",
            "is_customer_visible": True,
            "metadata": {"reason": reason},
            "created_at": now,
        })
        
        # TODO: Trigger refund if paid
        
        return True
    
    def get_order(self, order_id: str) -> Optional[OrderData]:
        """Get order by ID."""
        
        order = _orders_store.get(order_id)
        if not order:
            return None
        
        return self._order_to_data(order)
    
    def get_order_by_number(self, order_number: str) -> Optional[OrderData]:
        """Get order by order number."""
        
        order = next(
            (o for o in _orders_store.values() if o["order_number"] == order_number),
            None
        )
        if not order:
            return None
        
        return self._order_to_data(order)
    
    def list_orders(
        self,
        user_id: Optional[str] = None,
        company_id: Optional[str] = None,
        site_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[OrderData]:
        """List orders with filtering."""
        
        orders = list(_orders_store.values())
        
        if user_id:
            orders = [o for o in orders if o["user_id"] == user_id]
        if company_id:
            orders = [o for o in orders if o.get("company_id") == company_id]
        if site_id:
            orders = [o for o in orders if o.get("site_id") == site_id]
        if status:
            orders = [o for o in orders if o["status"] == status]
        
        # Sort by created_at descending
        orders.sort(key=lambda o: o["created_at"], reverse=True)
        
        return [self._order_to_data(o) for o in orders[:limit]]
    
    def _order_to_data(self, order: dict) -> OrderData:
        """Convert order dict to OrderData."""
        
        items = [
            OrderItemData(
                id=i["id"],
                product_id=i["product_id"],
                product_name=i["product_name"],
                product_type=i["product_type"],
                sku=i.get("sku"),
                quantity=i["quantity"],
                unit_price=i["unit_price"],
                total_price=i["total_price"],
                tax_rate=i.get("tax_rate", 0),
                tax_amount=i.get("tax_amount", 0),
                status=i.get("status", "pending"),
                scheduled_date=i.get("scheduled_date"),
                custom_options=i.get("custom_options", {}),
            )
            for i in order.get("items", [])
        ]
        
        events = [
            OrderEventData(
                id=e["id"],
                event_type=e["event_type"],
                title=e["title"],
                description=e.get("description"),
                actor_name=e.get("actor_name"),
                is_customer_visible=e.get("is_customer_visible", True),
                created_at=e["created_at"],
                metadata=e.get("metadata", {}),
            )
            for e in order.get("events", [])
        ]
        
        deliverables = [
            DeliverableData(
                id=d["id"],
                name=d["name"],
                description=d.get("description"),
                deliverable_type=d["deliverable_type"],
                file_size=d.get("file_size"),
                mime_type=d.get("mime_type"),
                download_url=d.get("download_url"),
                is_ready=d.get("is_ready", False),
                created_at=d["created_at"],
            )
            for d in order.get("deliverables", [])
        ]
        
        return OrderData(
            id=order["id"],
            order_number=order["order_number"],
            user_id=order["user_id"],
            company_id=order.get("company_id"),
            site_id=order.get("site_id"),
            project_name=order.get("project_name"),
            status=order["status"],
            payment_method=order.get("payment_method"),
            payment_reference=order.get("payment_reference"),
            currency=order.get("currency", "AOA"),
            subtotal=order["subtotal"],
            discount_amount=order.get("discount_amount", 0),
            coupon_code=order.get("coupon_code"),
            tax_amount=order.get("tax_amount", 0),
            delivery_cost=order.get("delivery_cost", 0),
            total=order["total"],
            items=items,
            events=events,
            deliverables=deliverables,
            delivery_method=order.get("delivery_method"),
            delivery_address=order.get("delivery_address"),
            assigned_team=order.get("assigned_team"),
            scheduled_start=order.get("scheduled_start"),
            estimated_delivery=order.get("estimated_delivery"),
            customer_notes=order.get("customer_notes"),
            created_at=order["created_at"],
            updated_at=order["updated_at"],
            completed_at=order.get("completed_at"),
        )


# Singleton
_order_service: Optional[OrderService] = None


def get_order_service() -> OrderService:
    """Get order service instance."""
    global _order_service
    if _order_service is None:
        _order_service = OrderService()
    return _order_service
